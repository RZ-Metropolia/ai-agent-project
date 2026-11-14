"""Tests for the logic behind the Streamlit page, without Streamlit.

Run from the project root: python -m unittest discover tests
"""

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from src import app_logic
from src.mcp_server.server import SESSION_ID
from tests.test_agent import AgentTestCase, ScriptedModel, answer, call
from tests.test_tools import FRIDAY

AWAITING = {"draft_id": 1, "status": "awaiting_customer_confirmation", "subtotal_eur": "16.00"}
CANCELLED = {"draft_id": 2, "status": "cancelled", "subtotal_eur": "9.50"}
CONFIRMED = {"draft_id": 3, "status": "confirmed", "subtotal_eur": "4.90"}
NOT_FOUND = {"ok": False, "error": {"code": "draft_not_found", "message": "Draft 9 was not found."}}


class SessionTests(unittest.TestCase):
    def test_session_ids_are_unique_and_accepted_by_the_mcp_server(self):
        first, second = app_logic.new_session_id(), app_logic.new_session_id()
        self.assertNotEqual(first, second)
        self.assertTrue(SESSION_ID.fullmatch(first))

    def test_context_uses_the_pages_inventory_api_and_session(self):
        with patch.dict(os.environ, {"SERVICE_DATE": "2026-11-06", "INVENTORY_TIMEOUT_SECONDS": "1.5"}):
            ctx = app_logic.build_context("http://127.0.0.1:9", "abc")
        self.assertEqual((ctx.inventory.base_url, ctx.inventory.timeout), ("http://127.0.0.1:9", 1.5))
        self.assertEqual((ctx.session_id, ctx.service_date), ("abc", FRIDAY))


class ModelTests(unittest.TestCase):
    def test_missing_key_gives_a_problem_and_no_model(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}), patch("src.app_logic.load_dotenv"):
            model, problem = app_logic.load_model()
        self.assertIsNone(model)
        self.assertIn("GROQ_API_KEY", problem)

    def test_with_a_key_the_groq_model_is_built(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
             patch("src.app_logic.build_model", return_value="model") as build_model:
            self.assertEqual(app_logic.load_model(), ("model", None))
        build_model.assert_called_once_with("groq")

    def test_model_name_can_be_set_in_the_environment(self):
        with patch.dict(os.environ, {"GROQ_MODEL": "qwen/other"}):
            self.assertEqual(app_logic.model_name(), "qwen/other")


class AskTests(AgentTestCase):
    def test_answer_and_history_for_the_next_request(self):
        model = ScriptedModel(call("search_menu", {"query": "sorbet"}), answer("Berry Sorbet, 4.90 EUR."))
        result, history = app_logic.ask(model, self.ctx, "Any sorbet?", [])
        self.assertEqual(result.answer, "Berry Sorbet, 4.90 EUR.")
        self.assertEqual([message.type for message in history], ["human", "ai", "tool", "ai"])

        _, history = app_logic.ask(ScriptedModel(answer("Yes.")), self.ctx, "Is it vegan?", history)
        self.assertEqual([message.type for message in history][-2:], ["human", "ai"])
        self.assertEqual(len(history), 6)


class TraceRowsTests(unittest.TestCase):
    def test_rows_show_the_tool_the_path_and_the_outcome(self):
        trace = [
            {"tool": "search_menu", "path": "direct", "args": {"query": "soup"},
             "result": {"ok": True, "items": []}},
            {"tool": "cancel_draft", "path": "mcp", "args": {"draft_id": 9}, "result": NOT_FOUND},
        ]
        self.assertEqual(app_logic.trace_rows(trace), [
            {"tool": "search_menu", "path": "Python tool", "arguments": '{"query": "soup"}',
             "outcome": "ok", "result": '{"ok": true, "items": []}'},
            {"tool": "cancel_draft", "path": "MCP server", "arguments": '{"draft_id": 9}',
             "outcome": "draft_not_found",
             "result": '{"ok": false, "error": {"code": "draft_not_found", "message": "Draft 9 was not found."}}'},
        ])

    def test_long_results_are_shortened(self):
        trace = [{"tool": "search_menu", "path": "direct", "args": {},
                  "result": {"ok": True, "items": ["x" * 2000]}}]
        result = app_logic.trace_rows(trace)[0]["result"]
        self.assertEqual(len(result), app_logic.RESULT_PREVIEW_CHARS + 1)
        self.assertTrue(result.endswith("…"))

    def test_no_tool_calls(self):
        self.assertEqual(app_logic.trace_rows([]), [])


class CartTests(AgentTestCase):
    def load_cart(self, result):
        with patch("src.mcp_client.list_drafts", return_value=result) as list_drafts:
            cart = app_logic.load_cart(self.ctx)
        list_drafts.assert_called_once_with(self.ctx)
        return cart

    def test_newest_draft_comes_first_with_labels(self):
        drafts, problem = self.load_cart({"ok": True, "drafts": [AWAITING, CANCELLED, CONFIRMED]})
        self.assertIsNone(problem)
        self.assertEqual([draft["draft_id"] for draft in drafts], [3, 2, 1])
        self.assertEqual([draft["status_label"] for draft in drafts],
                         ["Confirmed", "Cancelled", "Waiting for your confirmation"])

    def test_only_awaiting_drafts_can_be_changed(self):
        drafts, _ = self.load_cart({"ok": True, "drafts": [AWAITING, CANCELLED, CONFIRMED]})
        self.assertEqual([draft["can_change"] for draft in drafts], [False, False, True])

    def test_no_drafts(self):
        self.assertEqual(self.load_cart({"ok": True, "drafts": []}), ([], None))

    def test_unavailable_order_service_gives_a_problem_and_no_drafts(self):
        down = {"ok": False, "error": {"code": "mcp_unavailable",
                                       "message": "The order service is not available right now."}}
        self.assertEqual(self.load_cart(down), ([], "The order service is not available right now."))

    def test_real_mcp_server_fills_the_cart(self):
        from src import tools
        ctx = replace(self.ctx, session_id="alice")
        tools.draft_order(ctx, [{"name": "Lemonade", "quantity": 2}], "12:00")
        drafts, problem = app_logic.load_cart(ctx)
        self.assertIsNone(problem)
        self.assertEqual([(d["subtotal_eur"], d["can_change"]) for d in drafts], [("7.00", True)])


class ChangeDraftTests(AgentTestCase):
    def test_confirm_and_cancel_go_to_the_matching_mcp_tool(self):
        done = {"ok": True, "message": "Done."}
        with patch("src.mcp_client.confirm_draft", return_value=done) as confirm, \
             patch("src.mcp_client.cancel_draft", return_value=done) as cancel:
            self.assertEqual(app_logic.change_draft(self.ctx, "confirm", 1), (True, "Done."))
            self.assertEqual(app_logic.change_draft(self.ctx, "cancel", 2), (True, "Done."))
        confirm.assert_called_once_with(self.ctx, 1)
        cancel.assert_called_once_with(self.ctx, 2)

    def test_refusal_gives_the_reason(self):
        with patch("src.mcp_client.cancel_draft", return_value=NOT_FOUND):
            self.assertEqual(app_logic.change_draft(self.ctx, "cancel", 9), (False, "Draft 9 was not found."))

    def test_refused_confirmation_lists_every_problem(self):
        refused = {
            "ok": False,
            "error": {"code": "confirmation_refused", "message": "The draft was not confirmed."},
            "problems": [{"code": "sold_out", "message": "Margherita Pizza is sold out."},
                         {"code": "insufficient_stock", "message": "Only 1 portions of Lemonade are left."}],
        }
        with patch("src.mcp_client.confirm_draft", return_value=refused):
            succeeded, message = app_logic.change_draft(self.ctx, "confirm", 1)
        self.assertFalse(succeeded)
        self.assertEqual(message, "The draft was not confirmed. Margherita Pizza is sold out."
                                  " Only 1 portions of Lemonade are left.")

    def test_unknown_action_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            app_logic.change_draft(self.ctx, "pay", 1)


if __name__ == "__main__":
    unittest.main()
