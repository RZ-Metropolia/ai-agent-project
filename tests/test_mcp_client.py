"""Tests for the MCP client: result handling, server start-up settings, and real stdio calls.

Run from the project root: python -m unittest discover tests
"""

import asyncio
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src import mcp_client, tools
from src.config import ToolContext
from src.db import connect, init_db
from src.inventory_api import BackgroundServer
from src.inventory_client import InventoryClient, set_inventory_mode
from src.mcp_client import client
from tests.test_tools import FRIDAY, LEMONADE, PIZZA, FakeInventory


def mcp_result(*texts, is_error=False):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text) for text in texts], isError=is_error
    )


class ParseResultTests(unittest.TestCase):
    def test_tool_result_is_returned_as_a_dictionary(self):
        self.assertEqual(client.parse_result(mcp_result('{"ok": true, "drafts": []}')),
                         {"ok": True, "drafts": []})

    def test_tool_refusal_is_passed_on_unchanged(self):
        refusal = '{"ok": false, "error": {"code": "draft_not_found", "message": "Draft 9 was not found."}}'
        self.assertEqual(client.parse_result(mcp_result(refusal))["error"]["code"], "draft_not_found")

    def test_mcp_error_keeps_the_servers_message(self):
        result = client.parse_result(mcp_result("Unknown tool: pay", is_error=True))
        self.assertEqual(result["error"]["code"], "mcp_tool_error")
        self.assertIn("Unknown tool: pay", result["error"]["message"])

    def test_unexpected_content_is_an_error(self):
        other_block = SimpleNamespace(content=[SimpleNamespace(type="image")], isError=False)
        for result in (mcp_result("not json"), mcp_result("[1, 2]"), mcp_result('{"drafts": []}'),
                       mcp_result(), other_block):
            with self.subTest(result):
                self.assertEqual(client.parse_result(result)["error"]["code"], "mcp_bad_response")


class ClientTestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.db_path = init_db(Path(tmp_dir.name) / "test.db")
        self.ctx = self.context(FakeInventory())

    def context(self, inventory, **kwargs):
        return ToolContext(self.db_path, inventory, FRIDAY, ZoneInfo("Europe/Berlin"),
                           session_id="alice", **kwargs)

    def save_draft(self, ctx=None, pickup_time="18:30"):
        return tools.draft_order(ctx or self.ctx, [PIZZA, LEMONADE], pickup_time)["draft"]["draft_id"]

    def status(self, draft_id):
        with closing(connect(self.db_path, read_only=True)) as conn:
            return conn.execute("SELECT status FROM draft_orders WHERE id = ?", (draft_id,)).fetchone()[0]


class ServerParametersTests(ClientTestCase):
    def test_server_gets_the_database_and_service_day_of_the_context(self):
        parameters = client.server_parameters(self.ctx)
        self.assertEqual((parameters.command, parameters.args), (sys.executable, ["-m", "src.mcp_server"]))
        self.assertEqual(parameters.env, {
            "RESTAURANT_DB_PATH": str(self.db_path),
            "SERVICE_DATE": "2026-11-06",
            "RESTAURANT_TIMEZONE": "Europe/Berlin",
        })
        self.assertEqual(Path(parameters.cwd), client.PROJECT_ROOT)

    def test_server_gets_the_inventory_api_address(self):
        ctx = self.context(InventoryClient("http://127.0.0.1:9/", timeout=1.5))
        env = client.server_parameters(ctx).env
        self.assertEqual((env["INVENTORY_API_URL"], env["INVENTORY_TIMEOUT_SECONDS"]),
                         ("http://127.0.0.1:9", "1.5"))

    def test_custom_server_command(self):
        parameters = client.server_parameters(replace(self.ctx, order_service_command=("server", "--x")))
        self.assertEqual((parameters.command, parameters.args), ("server", ["--x"]))


class SessionWrapperTests(ClientTestCase):
    def test_wrappers_send_the_session_of_the_context(self):
        with patch("src.mcp_client.client.call_tool", return_value={"ok": True}) as call_tool:
            mcp_client.list_drafts(self.ctx)
            mcp_client.cancel_draft(self.ctx, 3)
            mcp_client.confirm_draft(self.ctx, 4)
        self.assertEqual([call.args[1:] for call in call_tool.call_args_list], [
            ("list_drafts", {"session_id": "alice"}),
            ("cancel_draft", {"session_id": "alice", "draft_id": 3}),
            ("confirm_draft", {"session_id": "alice", "draft_id": 4}),
        ])


class RealServerTests(ClientTestCase):
    """The client against a real MCP server process over stdio."""

    @classmethod
    def setUpClass(cls):
        cls.inventory = BackgroundServer().start()
        cls.addClassCleanup(cls.inventory.stop)

    def setUp(self):
        super().setUp()
        self.ctx = self.context(InventoryClient(self.inventory.url))
        self.addCleanup(set_inventory_mode, self.inventory.url, "normal")

    def test_server_offers_its_three_tools(self):
        self.assertEqual(mcp_client.list_tool_names(self.ctx),
                         ["list_drafts", "cancel_draft", "confirm_draft"])

    def test_list_cancel_and_confirm_change_the_database(self):
        first, second = self.save_draft(), self.save_draft(pickup_time="19:00")
        listed = mcp_client.list_drafts(self.ctx)
        self.assertEqual([draft["draft_id"] for draft in listed["drafts"]], [first, second])

        self.assertEqual(mcp_client.cancel_draft(self.ctx, first)["draft"]["status"], "cancelled")
        self.assertEqual(mcp_client.confirm_draft(self.ctx, second)["draft"]["status"], "confirmed")
        self.assertEqual((self.status(first), self.status(second)), ("cancelled", "confirmed"))

    def test_no_matching_draft(self):
        self.assertEqual(mcp_client.list_drafts(self.ctx), {"ok": True, "drafts": []})
        self.assertEqual(mcp_client.cancel_draft(self.ctx, 99)["error"]["code"], "draft_not_found")

    def test_other_session_cannot_change_a_draft(self):
        draft_id = self.save_draft()
        result = mcp_client.cancel_draft(replace(self.ctx, session_id="bob"), draft_id)
        self.assertEqual(result["error"]["code"], "draft_not_found")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_confirm_fails_closed_when_the_inventory_api_is_down(self):
        draft_id = self.save_draft()
        set_inventory_mode(self.inventory.url, "outage")
        result = mcp_client.confirm_draft(self.ctx, draft_id)
        self.assertEqual(result["problems"][0]["code"], "inventory_unavailable")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_invalid_parameters_and_unknown_tools_are_tool_errors(self):
        draft_id = self.save_draft()
        calls = (("cancel_draft", {"session_id": "alice", "draft_id": "one"}),
                 ("cancel_draft", {"draft_id": draft_id}),
                 ("pay_order", {}))
        for name, arguments in calls:
            with self.subTest(name=name, arguments=arguments):
                result = mcp_client.call_tool(self.ctx, name, arguments)
                self.assertEqual(result["error"]["code"], "mcp_tool_error")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_server_that_cannot_start_is_unavailable(self):
        commands = (("order-service-that-does-not-exist",), (sys.executable, "-c", "raise SystemExit(1)"))
        for command in commands:
            with self.subTest(command):
                result = mcp_client.list_drafts(replace(self.ctx, order_service_command=command))
                self.assertEqual(result["error"]["code"], "mcp_unavailable")

    def test_server_that_does_not_answer_is_unavailable_after_the_timeout(self):
        silent = replace(self.ctx, order_service_command=(sys.executable, "-c", "import time; time.sleep(30)"))
        with patch.object(client, "CALL_TIMEOUT_SECONDS", 1.0):
            result = mcp_client.list_drafts(silent)
        self.assertEqual(result["error"]["code"], "mcp_unavailable")

    def test_client_works_inside_a_running_event_loop(self):
        # A notebook cell runs inside an event loop, where asyncio.run() is not allowed.
        async def notebook_cell():
            return mcp_client.list_drafts(self.ctx)

        self.assertEqual(asyncio.run(notebook_cell()), {"ok": True, "drafts": []})


if __name__ == "__main__":
    unittest.main()
