"""Tests for the order-draft rules: list, cancel, and confirm.

Run from the project root: python -m unittest discover tests
"""

from contextlib import closing
from dataclasses import replace
from datetime import timedelta

from src import orders, tools
from src.db import connect
from tests.test_tools import LEMONADE, PIZZA, FakeInventory, ToolTestCase


class OrderTestCase(ToolTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = replace(self.ctx, session_id="alice")
        self.other = replace(self.ctx, session_id="bob")

    def save_draft(self, ctx=None, items=(PIZZA, LEMONADE), pickup_time="18:30", **kwargs):
        result = tools.draft_order(ctx or self.ctx, list(items), pickup_time, **kwargs)
        self.assertTrue(result["ok"], result)
        return result["draft"]["draft_id"]

    def status(self, draft_id):
        return self.query("SELECT status FROM draft_orders WHERE id = ?", (draft_id,))[0][0]


class SessionTests(OrderTestCase):
    def test_draft_order_stores_the_session(self):
        draft_id = self.save_draft()
        self.assertEqual(
            self.query("SELECT session_id FROM draft_orders WHERE id = ?", (draft_id,)), [("alice",)]
        )

    def test_identical_orders_in_two_sessions_are_two_drafts(self):
        first = self.save_draft()
        second = tools.draft_order(self.other, [PIZZA, LEMONADE], "18:30")
        self.assertFalse(second["already_existed"])
        self.assertNotEqual(second["draft"]["draft_id"], first)

    def test_identical_retry_in_one_session_is_still_one_draft(self):
        first = self.save_draft()
        self.assertEqual(self.save_draft(), first)
        self.assertEqual(self.draft_count(), 1)


class ListDraftsTests(OrderTestCase):
    def test_no_drafts_is_an_empty_list(self):
        self.assertEqual(orders.list_drafts(self.ctx), {"ok": True, "drafts": []})

    def test_lists_only_this_session_oldest_first(self):
        first = self.save_draft()
        self.save_draft(self.other)
        second = self.save_draft(pickup_time="19:00")
        drafts = orders.list_drafts(self.ctx)["drafts"]
        self.assertEqual([draft["draft_id"] for draft in drafts], [first, second])

    def test_draft_shape(self):
        self.save_draft(budget_eur=20)
        self.assertEqual(
            orders.list_drafts(self.ctx)["drafts"][0],
            {
                "draft_id": 1,
                "status": "awaiting_customer_confirmation",
                "service_date": "2026-11-06",
                "pickup_time": "18:30",
                "lines": [
                    {"name": "Margherita Pizza", "quantity": 1, "unit_price_eur": "12.50",
                     "unit_price_cents": 1250, "line_total_eur": "12.50", "line_total_cents": 1250},
                    {"name": "Lemonade", "quantity": 1, "unit_price_eur": "3.50",
                     "unit_price_cents": 350, "line_total_eur": "3.50", "line_total_cents": 350},
                ],
                "subtotal_eur": "16.00",
                "subtotal_cents": 1600,
                "budget_eur": "20.00",
            },
        )

    def test_prices_are_the_prices_when_the_draft_was_made(self):
        self.save_draft()
        with closing(connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE menu_items SET price_cents = 9999 WHERE name = 'Lemonade'")
        draft = orders.list_drafts(self.ctx)["drafts"][0]
        self.assertEqual(draft["lines"][1]["unit_price_eur"], "3.50")
        self.assertEqual(draft["subtotal_eur"], "16.00")

    def test_missing_database_is_an_error(self):
        ctx = replace(self.ctx, db_path=self.db_path.with_name("missing.db"))
        self.assert_error(orders.list_drafts(ctx), "database_error")


class CancelDraftTests(OrderTestCase):
    def test_cancel_changes_the_status(self):
        draft_id = self.save_draft()
        result = orders.cancel_draft(self.ctx, draft_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["draft"]["status"], "cancelled")
        self.assertEqual(self.status(draft_id), "cancelled")

    def test_unknown_draft_is_not_found(self):
        self.assert_error(orders.cancel_draft(self.ctx, 99), "draft_not_found")

    def test_other_sessions_draft_is_not_found_and_unchanged(self):
        draft_id = self.save_draft()
        self.assert_error(orders.cancel_draft(self.other, draft_id), "draft_not_found")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_draft_cannot_be_cancelled_twice(self):
        draft_id = self.save_draft()
        orders.cancel_draft(self.ctx, draft_id)
        result = orders.cancel_draft(self.ctx, draft_id)
        self.assert_error(result, "draft_not_awaiting")
        self.assertEqual(result["status"], "cancelled")

    def test_confirmed_draft_cannot_be_cancelled(self):
        draft_id = self.save_draft()
        orders.confirm_draft(self.ctx, draft_id)
        self.assert_error(orders.cancel_draft(self.ctx, draft_id), "draft_not_awaiting")
        self.assertEqual(self.status(draft_id), "confirmed")

    def test_invalid_draft_numbers_are_refused(self):
        for draft_id in (0, -1, "1", 1.0, True, None):
            with self.subTest(draft_id):
                self.assert_error(orders.cancel_draft(self.ctx, draft_id), "invalid_argument")

    def test_cancelled_draft_does_not_block_the_same_order_again(self):
        first = self.save_draft()
        orders.cancel_draft(self.ctx, first)
        self.assertNotEqual(self.save_draft(), first)


class ConfirmDraftTests(OrderTestCase):
    def test_confirm_changes_the_status_and_says_no_payment(self):
        draft_id = self.save_draft()
        result = orders.confirm_draft(self.ctx, draft_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["draft"]["status"], "confirmed")
        self.assertIn("No payment", result["message"])
        self.assertEqual(self.status(draft_id), "confirmed")

    def test_unknown_or_other_sessions_draft_is_not_found(self):
        draft_id = self.save_draft()
        self.assert_error(orders.confirm_draft(self.ctx, 99), "draft_not_found")
        self.assert_error(orders.confirm_draft(self.other, draft_id), "draft_not_found")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_draft_cannot_be_confirmed_twice_or_after_cancelling(self):
        confirmed = self.save_draft()
        orders.confirm_draft(self.ctx, confirmed)
        self.assert_error(orders.confirm_draft(self.ctx, confirmed), "draft_not_awaiting")
        cancelled = self.save_draft(pickup_time="19:00")
        orders.cancel_draft(self.ctx, cancelled)
        self.assert_error(orders.confirm_draft(self.ctx, cancelled), "draft_not_awaiting")
        self.assertEqual(self.status(cancelled), "cancelled")

    def test_sold_out_since_the_draft_refuses(self):
        draft_id = self.save_draft()
        ctx = replace(self.ctx, inventory=FakeInventory(portions={1: 0, 17: 20}))
        result = orders.confirm_draft(ctx, draft_id)
        self.assert_error(result, "confirmation_refused")
        self.assertEqual([problem["code"] for problem in result["problems"]], ["sold_out"])
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_too_little_stock_refuses(self):
        draft_id = self.save_draft(items=[{"name": "Margherita Pizza", "quantity": 3}])
        ctx = replace(self.ctx, inventory=FakeInventory(portions={1: 2}))
        result = orders.confirm_draft(ctx, draft_id)
        self.assertEqual([problem["code"] for problem in result["problems"]], ["insufficient_stock"])
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_api_failure_fails_closed(self):
        draft_id = self.save_draft()
        ctx = replace(self.ctx, inventory=FakeInventory(failure="the inventory service returned HTTP 503"))
        result = orders.confirm_draft(ctx, draft_id)
        self.assert_error(result, "confirmation_refused")
        self.assertEqual([problem["code"] for problem in result["problems"]], ["inventory_unavailable"])
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_draft_from_another_day_is_refused(self):
        draft_id = self.save_draft()
        tomorrow = replace(self.ctx, service_date=self.ctx.service_date + timedelta(days=1))
        self.assert_error(orders.confirm_draft(tomorrow, draft_id), "draft_expired")
        self.assertEqual(self.status(draft_id), "awaiting_customer_confirmation")

    def test_invalid_draft_numbers_are_refused(self):
        for draft_id in (0, "1", True, None):
            with self.subTest(draft_id):
                self.assert_error(orders.confirm_draft(self.ctx, draft_id), "invalid_argument")
