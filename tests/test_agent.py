"""Tests for the tool executor, the agent loop, the XML parser, and the evaluation checks.

A scripted fake model replaces Groq and local Qwen, so no API key or GPU is needed.
Run from the project root: python -m unittest discover tests
"""

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src import agent
from src.agent import run_agent, strip_thinking
from src.agent_tools import execute_tool, make_tools
from src.config import ToolContext
from src.db import connect, init_db
from src.evaluation import SCENARIOS, run_scenario, says_amount
from src.inventory_api import BackgroundServer
from src.local_model import parse_tool_calls, to_chat_messages
from tests.test_tools import FRIDAY, FakeInventory

SALMON_TOTAL = {"items": [{"name": "Grilled Salmon", "quantity": 2}], "budget_eur": 30}


def call(name, args, call_id="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def answer(text):
    return AIMessage(content=text)


class ScriptedModel:
    """Plays back fixed replies, like a model that always makes the same choices."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return self.replies.pop(0)


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.db_path = init_db(Path(tmp_dir.name) / "test.db")
        self.ctx = ToolContext(
            db_path=self.db_path,
            inventory=FakeInventory(),
            service_date=FRIDAY,
            timezone=ZoneInfo("Europe/Berlin"),
        )
        self.tools = make_tools(self.ctx)

    def draft_count(self):
        with closing(connect(self.db_path, read_only=True)) as conn:
            return conn.execute("SELECT COUNT(*) FROM draft_orders").fetchone()[0]


class ExecutorTests(AgentTestCase):
    def test_registry_has_the_six_tools(self):
        self.assertEqual(
            list(self.tools),
            ["search_menu", "filter_dietary_options", "get_ingredients",
             "check_availability", "calculate_total", "draft_order"],
        )

    def test_valid_call_returns_the_tool_result(self):
        result = execute_tool(self.tools, "calculate_total", SALMON_TOTAL)
        self.assertEqual(result["subtotal_eur"], "39.80")

    def test_unknown_tool_is_refused(self):
        result = execute_tool(self.tools, "pay_order", {})
        self.assertEqual(result["error"]["code"], "unknown_tool")

    def test_invalid_arguments_are_refused_and_nothing_is_saved(self):
        bad_calls = [
            {"items": [{"name": "Falafel Wrap", "quantity": 0}], "pickup_time": "18:00"},
            {"items": [], "pickup_time": "18:00"},
            {"items": "Falafel Wrap", "pickup_time": "18:00"},
            {"pickup_time": "18:00"},
            "not a dictionary",
        ]
        for args in bad_calls:
            with self.subTest(args=args):
                result = execute_tool(self.tools, "draft_order", args)
                self.assertEqual(result["error"]["code"], "invalid_argument")
        self.assertEqual(self.draft_count(), 0)

    def test_model_cannot_set_the_context(self):
        result = execute_tool(
            self.tools, "filter_dietary_options", {"service_date": "2026-11-07", "db_path": "x.db"}
        )
        self.assertEqual(result["error"]["code"], "invalid_argument")
        self.assertIn("service_date", result["error"]["message"])

    def test_schemas_do_not_show_the_context(self):
        for tool in make_tools(None).values():
            self.assertNotIn("ctx", tool.args_schema.model_json_schema()["properties"])


class AgentLoopTests(AgentTestCase):
    def test_tool_result_reaches_the_model_and_the_trace(self):
        model = ScriptedModel(call("calculate_total", SALMON_TOTAL), answer("The total is 39.80 EUR."))
        result = run_agent(model, self.ctx, self.tools, "2 salmon, budget 30")

        self.assertEqual(result.answer, "The total is 39.80 EUR.")
        self.assertEqual(result.stop_reason, "answer")
        self.assertEqual([step["tool"] for step in result.trace], ["calculate_total"])
        self.assertEqual(result.trace[0]["result"]["over_budget_by_eur"], "9.80")
        tool_message = result.messages[3]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertEqual(json.loads(tool_message.content)["subtotal_eur"], "39.80")

    def test_refusal_is_given_back_to_the_model(self):
        model = ScriptedModel(call("pay_order", {}), answer("I cannot pay."))
        result = run_agent(model, self.ctx, self.tools, "pay")
        self.assertEqual(result.trace[0]["result"]["error"]["code"], "unknown_tool")
        self.assertEqual(result.answer, "I cannot pay.")

    def test_round_limit_stops_the_loop(self):
        replies = [call("search_menu", {}, f"call_{n}") for n in range(agent.MAX_ROUNDS + 1)]
        model = ScriptedModel(*replies)
        result = run_agent(model, self.ctx, self.tools, "menu")
        self.assertEqual(result.stop_reason, "round_limit")
        self.assertEqual(model.calls, agent.MAX_ROUNDS)

    def test_tool_call_limit_stops_before_running_the_calls(self):
        many = AIMessage(
            content="",
            tool_calls=[
                {"name": "search_menu", "args": {}, "id": f"call_{n}"}
                for n in range(agent.MAX_TOOL_CALLS + 1)
            ],
        )
        result = run_agent(ScriptedModel(many), self.ctx, self.tools, "menu")
        self.assertEqual(result.stop_reason, "tool_limit")
        self.assertEqual(result.trace, [])
        self.assertIsInstance(result.messages[-1], HumanMessage)

    def test_model_error_gives_an_answer_instead_of_a_crash(self):
        class BrokenModel:
            def invoke(self, messages):
                raise ConnectionError("no network")

        result = run_agent(BrokenModel(), self.ctx, self.tools, "menu")
        self.assertEqual(result.stop_reason, "model_error")
        self.assertIn("no network", result.answer)

    def test_history_is_kept_between_turns(self):
        first = run_agent(ScriptedModel(answer("Hello.")), self.ctx, self.tools, "Hi")
        second = run_agent(ScriptedModel(answer("Yes.")), self.ctx, self.tools, "And?", first.messages[1:])
        self.assertEqual([m.content for m in second.messages[1:]], ["Hi", "Hello.", "And?", "Yes."])

    def test_system_prompt_has_the_pickup_hours(self):
        result = run_agent(ScriptedModel(answer("Hi.")), self.ctx, self.tools, "Hi")
        self.assertIn("11:00-21:00", result.messages[0].content)

    def test_thinking_is_removed_from_the_answer(self):
        self.assertEqual(strip_thinking("<think>\nmaybe\n</think>\n\nThe total is 39.80 EUR."),
                         "The total is 39.80 EUR.")


class XmlParserTests(unittest.TestCase):
    def test_parses_qwen_tool_calls(self):
        text = (
            "I will calculate it.\n<tool_call>\n<function=calculate_total>\n"
            '<parameter=items>\n[{"name": "Grilled Salmon", "quantity": 2}]\n</parameter>\n'
            "<parameter=budget_eur>\n30\n</parameter>\n</function>\n</tool_call>"
        )
        content, calls = parse_tool_calls(text)
        self.assertEqual(content, "I will calculate it.")
        self.assertEqual(calls[0]["name"], "calculate_total")
        self.assertEqual(calls[0]["args"], SALMON_TOTAL)

    def test_text_values_and_several_calls(self):
        text = (
            "<tool_call>\n<function=get_ingredients>\n<parameter=item_name>\nVegan Thai Curry\n"
            "</parameter>\n</function>\n</tool_call>\n<tool_call>\n<function=draft_order>\n"
            "<parameter=pickup_time>\n18:30\n</parameter>\n</function>\n</tool_call>"
        )
        _, calls = parse_tool_calls(text)
        self.assertEqual([c["args"] for c in calls],
                         [{"item_name": "Vegan Thai Curry"}, {"pickup_time": "18:30"}])
        self.assertNotEqual(calls[0]["id"], calls[1]["id"])

    def test_plain_answer_has_no_calls(self):
        self.assertEqual(parse_tool_calls("<think>\n\n</think>\n\nHello!"), ("Hello!", []))

    def test_broken_call_becomes_an_unknown_tool(self):
        _, calls = parse_tool_calls("<tool_call>\n{oops}\n</tool_call>")
        self.assertEqual(calls[0]["name"], "malformed_tool_call")

    def test_messages_for_the_chat_template(self):
        chat = to_chat_messages([
            SystemMessage("rules"),
            HumanMessage("hi"),
            call("search_menu", {"query": "soup"}),
            ToolMessage('{"ok": true}', tool_call_id="call_1"),
        ])
        self.assertEqual([m["role"] for m in chat], ["system", "user", "assistant", "tool"])
        self.assertEqual(chat[2]["tool_calls"][0]["function"],
                         {"name": "search_menu", "arguments": {"query": "soup"}})


PIZZA_AND_LEMONADE = [{"name": "Margherita Pizza", "quantity": 1}, {"name": "Lemonade", "quantity": 1}]

# What a good model does in each scenario: tool calls, then an answer from the tool results.
GOOD_RUNS = {
    "E-01": [
        call("filter_dietary_options", {"required_labels": ["vegetarian"]}),
        call("check_availability", {"items": PIZZA_AND_LEMONADE}),
        call("draft_order", {"items": PIZZA_AND_LEMONADE, "pickup_time": "18:30",
                             "required_labels": ["vegetarian"], "budget_eur": 20}),
        answer("Draft saved: Margherita Pizza and Lemonade, total 16.00 EUR. Please confirm it."),
    ],
    "E-02": [
        call("filter_dietary_options", {"required_labels": ["vegan", "gluten_free"], "category": "main"}),
        answer("Today only the Vegan Thai Curry is both vegan and gluten-free."),
    ],
    "E-03": [
        call("get_ingredients", {"item_name": "Vegan Thai Curry"}),
        answer("No. The Vegan Thai Curry contains peanuts (and soy), so it is not safe for you."),
    ],
    "E-04": [
        call("check_availability", {"items": [{"name": "Mushroom Risotto", "quantity": 1}]}),
        answer("Sorry, the Mushroom Risotto is sold out today."),
    ],
    "E-05": [
        call("filter_dietary_options", {"required_labels": ["vegan"], "category": "dessert",
                                        "max_price_eur": 4}),
        answer("No vegan dessert costs less than 4 euros. The Berry Sorbet is vegan and costs 4.90 EUR."),
    ],
    "E-06": [
        call("draft_order", {"items": [{"name": "Margherita Pizza", "quantity": 1}],
                             "pickup_time": "18:30"}),
        answer("Sorry, availability could not be checked right now, so no draft was saved."),
    ],
    "E-07": [
        call("calculate_total", {"items": [{"name": "Grilled Salmon", "quantity": 2}], "budget_eur": 30}),
        answer("The total is 39.80 EUR, which is 9.80 EUR over your budget. No draft was saved."),
    ],
    "E-08": [
        call("draft_order", {"items": [{"name": "Falafel Wrap", "quantity": 1}], "pickup_time": "23:30"}),
        answer("23:30 is outside the pickup hours 11:00-21:00. Please choose another time."),
    ],
}


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = BackgroundServer().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_good_model_passes_every_scenario(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario.id):
                row = run_scenario(ScriptedModel(*GOOD_RUNS[scenario.id]), scenario, self.server.url)
                self.assertEqual(row["result"], "Pass", row["checks"])

    def test_model_that_skips_the_tools_fails_every_scenario(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario.id):
                row = run_scenario(ScriptedModel(answer("Sure, done!")), scenario, self.server.url)
                self.assertEqual(row["result"], "Fail")

    def test_missing_non_critical_fact_is_partial(self):
        scenario = next(s for s in SCENARIOS if s.id == "E-07")
        model = ScriptedModel(GOOD_RUNS["E-07"][0], answer("The total is 39.80 EUR. No draft."))
        self.assertEqual(run_scenario(model, scenario, self.server.url)["result"], "Partial")

    def test_outage_is_switched_off_after_the_scenario(self):
        scenario = next(s for s in SCENARIOS if s.id == "E-06")
        run_scenario(ScriptedModel(*GOOD_RUNS["E-06"]), scenario, self.server.url)
        e01 = next(s for s in SCENARIOS if s.id == "E-01")
        self.assertEqual(
            run_scenario(ScriptedModel(*GOOD_RUNS["E-01"]), e01, self.server.url)["result"], "Pass"
        )

    def test_amounts_are_not_found_inside_other_amounts(self):
        self.assertTrue(says_amount("over by 9,80 EUR", "9.80"))
        self.assertFalse(says_amount("total 39.80 EUR", "9.80"))


if __name__ == "__main__":
    unittest.main()
