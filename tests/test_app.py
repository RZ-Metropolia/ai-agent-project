"""Tests that run the Streamlit page itself, with a scripted model in place of Qwen.

The page, the tools, the inventory API, the MCP client, and the MCP server are all real.
Run from the project root: python -m unittest discover tests
"""

import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.db import connect
from tests.test_agent import PIZZA_AND_LEMONADE, ScriptedModel, answer, call

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
DRAFT_CALL = call("draft_order", {"items": PIZZA_AND_LEMONADE, "pickup_time": "18:30",
                                  "required_labels": ["vegetarian"], "budget_eur": 20})
DRAFT_ANSWER = "Your draft is ready: Margherita Pizza and Lemonade, 16.00 EUR. Please confirm it."


class AppTests(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.db_path = Path(tmp_dir.name) / "app.db"
        environment = patch.dict(os.environ, {
            "RESTAURANT_DB_PATH": str(self.db_path), "SERVICE_DATE": "2026-11-06",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def open_page(self, *replies, problem=None):
        model = None if problem else ScriptedModel(*replies)
        loader = patch("src.app_logic.load_model", return_value=(model, problem))
        loader.start()
        self.addCleanup(loader.stop)
        page = AppTest.from_file(APP_PATH, default_timeout=120).run()
        self.assertFalse(page.exception, page.exception)
        return page

    def ask(self, page, request):
        page.chat_input[0].set_value(request).run()
        self.assertFalse(page.exception, page.exception)

    def sidebar_text(self, page):
        elements = [*page.sidebar.markdown, *page.sidebar.caption, *page.sidebar.text]
        return "\n".join(element.value for element in elements)

    def statuses(self):
        with closing(connect(self.db_path, read_only=True)) as conn:
            return [row[0] for row in conn.execute("SELECT status FROM draft_orders ORDER BY id")]

    def test_first_view_creates_the_database_and_shows_the_service_day(self):
        page = self.open_page()
        self.assertTrue(self.db_path.exists())
        self.assertEqual(page.title[0].value, "Restaurant Order Agent")
        self.assertIn("Friday 2026-11-06", self.sidebar_text(page))
        self.assertIn("No drafts yet", self.sidebar_text(page))
        self.assertEqual(len(page.chat_message), 0)

    def test_request_shows_the_answer_the_tool_calls_and_the_draft(self):
        page = self.open_page(DRAFT_CALL, answer(DRAFT_ANSWER))
        self.ask(page, "A vegetarian main and a drink at 18:30, at most 20 euros.")

        self.assertEqual([message.name for message in page.chat_message], ["user", "assistant"])
        self.assertEqual(page.chat_message[1].markdown[0].value, DRAFT_ANSWER)
        self.assertEqual(page.expander[0].label, "Tool calls (1)")
        self.assertIn("draft_order", page.expander[0].markdown[0].value)
        self.assertIn("Python tool", page.expander[0].markdown[0].value)

        text = self.sidebar_text(page)
        for expected in ("Draft #1", "pickup 18:30", "Waiting for your confirmation",
                         "1 × Margherita Pizza  12.50 €", "Total 16.00 €"):
            self.assertIn(expected, text)
        self.assertEqual(self.statuses(), ["awaiting_customer_confirmation"])

    def test_confirm_button_confirms_through_the_mcp_server(self):
        page = self.open_page(DRAFT_CALL, answer(DRAFT_ANSWER))
        self.ask(page, "Order a pizza and a lemonade for 18:30.")
        page.button(key="confirm_1").click().run()

        self.assertEqual(self.statuses(), ["confirmed"])
        self.assertIn("No payment was made", page.sidebar.success[0].value)
        self.assertIn("Confirmed", self.sidebar_text(page))
        self.assertEqual([button.key for button in page.sidebar.button], [])

    def test_cancel_button_cancels_through_the_mcp_server(self):
        page = self.open_page(DRAFT_CALL, answer(DRAFT_ANSWER))
        self.ask(page, "Order a pizza and a lemonade for 18:30.")
        page.button(key="cancel_1").click().run()

        self.assertEqual(self.statuses(), ["cancelled"])
        self.assertIn("Draft 1 was cancelled", page.sidebar.success[0].value)

    def test_confirm_is_refused_during_an_inventory_outage(self):
        page = self.open_page(DRAFT_CALL, answer(DRAFT_ANSWER))
        self.ask(page, "Order a pizza and a lemonade for 18:30.")
        page.sidebar.toggle[0].set_value(True).run()
        self.addCleanup(lambda: page.sidebar.toggle[0].set_value(False).run())
        page.button(key="confirm_1").click().run()

        self.assertEqual(self.statuses(), ["awaiting_customer_confirmation"])
        self.assertIn("Availability could not be checked", page.sidebar.error[0].value)
        self.assertEqual(len(page.sidebar.button), 2)  # The draft can still be confirmed later.

    def test_assistant_cancels_a_draft_through_mcp_and_the_cart_follows(self):
        page = self.open_page(
            DRAFT_CALL, answer(DRAFT_ANSWER),
            call("list_drafts", {}), call("cancel_draft", {"draft_id": 1}, "call_2"),
            answer("Draft 1 was cancelled."),
        )
        self.ask(page, "Order a pizza and a lemonade for 18:30.")
        self.ask(page, "Please cancel my draft.")

        self.assertEqual(self.statuses(), ["cancelled"])
        self.assertEqual(page.expander[1].label, "Tool calls (2)")
        self.assertTrue(all("MCP server" in row.value for row in page.expander[1].markdown))
        self.assertIn("Cancelled", self.sidebar_text(page))

    def test_example_button_sends_its_request(self):
        page = self.open_page(answer("Only the Vegan Thai Curry."))
        page.button(key="example_1").click().run()
        self.assertEqual(page.chat_message[0].markdown[0].value,
                         "Which main courses are both vegan and gluten-free today?")
        self.assertEqual(page.chat_message[1].markdown[0].value, "Only the Vegan Thai Curry.")

    def test_model_error_shows_a_friendly_answer(self):
        page = self.open_page(ConnectionError("no network"))
        self.ask(page, "Hello")
        self.assertIn("Please try again", page.chat_message[1].markdown[0].value)
        self.assertIn("no network", page.chat_message[1].caption[0].value)

    def test_missing_key_shows_what_to_do_and_no_chat(self):
        page = self.open_page(problem="GROQ_API_KEY is not set.")
        self.assertEqual(page.error[0].value, "GROQ_API_KEY is not set.")
        self.assertEqual(len(page.chat_input), 0)


if __name__ == "__main__":
    unittest.main()
