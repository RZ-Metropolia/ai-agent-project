"""Tests for the functions that the MCP server exposes, called directly without a client.

Run from the project root: python -m unittest discover tests
"""

import asyncio
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from src import tools
from src.config import load_context
from src.db import connect, init_db
from src.inventory_api import BackgroundServer
from src.inventory_client import set_inventory_mode
from src.mcp_server import server
from tests.test_tools import LEMONADE, PIZZA


class McpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = BackgroundServer().start()
        cls.addClassCleanup(cls.inventory.stop)

    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.db_path = init_db(Path(tmp_dir.name) / "test.db")
        # The server reads its settings from the environment, as it does when the client starts it.
        environment = patch.dict(os.environ, {
            "RESTAURANT_DB_PATH": str(self.db_path),
            "SERVICE_DATE": "2026-11-06",
            "INVENTORY_API_URL": self.inventory.url,
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(set_inventory_mode, self.inventory.url, "normal")

    def save_draft(self, session_id):
        ctx = server.replace(load_context(), session_id=session_id)
        return tools.draft_order(ctx, [PIZZA, LEMONADE], "18:30")["draft"]["draft_id"]

    def status(self, draft_id):
        with closing(connect(self.db_path, read_only=True)) as conn:
            return conn.execute("SELECT status FROM draft_orders WHERE id = ?", (draft_id,)).fetchone()[0]

    def test_server_exposes_three_tools_that_need_a_session(self):
        listed = asyncio.run(server.mcp.list_tools())
        self.assertEqual([tool.name for tool in listed], ["list_drafts", "cancel_draft", "confirm_draft"])
        for tool in listed:
            self.assertIn("session_id", tool.inputSchema["required"])
            self.assertTrue(tool.description)

    def test_list_drafts_returns_the_sessions_drafts(self):
        draft_id = self.save_draft("alice")
        result = server.list_drafts("alice")
        self.assertEqual([draft["draft_id"] for draft in result["drafts"]], [draft_id])
        self.assertEqual(result["drafts"][0]["subtotal_eur"], "16.00")

    def test_list_drafts_without_drafts_is_empty(self):
        self.assertEqual(server.list_drafts("alice"), {"ok": True, "drafts": []})

    def test_sessions_do_not_see_or_change_each_other(self):
        draft_id = self.save_draft("alice")
        self.assertEqual(server.list_drafts("bob")["drafts"], [])
        self.assertEqual(server.cancel_draft("bob", draft_id)["error"]["code"], "draft_not_found")
        self.assertEqual(server.confirm_draft("bob", draft_id)["error"]["code"], "draft_not_found")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_cancel_draft(self):
        draft_id = self.save_draft("alice")
        self.assertEqual(server.cancel_draft("alice", draft_id)["draft"]["status"], "cancelled")
        self.assertEqual(self.status(draft_id), "cancelled")

    def test_cancel_unknown_draft_is_not_found(self):
        self.assertEqual(server.cancel_draft("alice", 99)["error"]["code"], "draft_not_found")

    def test_confirm_draft_checks_stock_through_the_inventory_api(self):
        draft_id = self.save_draft("alice")
        result = server.confirm_draft("alice", draft_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.status(draft_id), "confirmed")

    def test_confirm_is_refused_while_the_inventory_api_is_down(self):
        draft_id = self.save_draft("alice")
        set_inventory_mode(self.inventory.url, "outage")
        result = server.confirm_draft("alice", draft_id)
        self.assertEqual(result["error"]["code"], "confirmation_refused")
        self.assertEqual(result["problems"][0]["code"], "inventory_unavailable")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_invalid_session_ids_are_refused(self):
        draft_id = self.save_draft("alice")
        for session_id in ("", " ", "a b", "alice'; --", "x" * 65, None, 5):
            with self.subTest(session_id):
                for result in (server.list_drafts(session_id), server.cancel_draft(session_id, draft_id)):
                    self.assertEqual(result["error"]["code"], "invalid_argument")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_missing_database_is_an_error_result(self):
        with patch.dict(os.environ, {"RESTAURANT_DB_PATH": str(self.db_path.with_name("missing.db"))}):
            self.assertEqual(server.list_drafts("alice")["error"]["code"], "database_error")


if __name__ == "__main__":
    unittest.main()
