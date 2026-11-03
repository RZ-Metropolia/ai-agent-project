"""Tests for the six tools, and the evaluation scenarios without a model.

Run from the project root: python -m unittest discover tests
"""

import json
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from src import tools
from src.config import ToolContext
from src.db import connect, init_db
from src.inventory_api import INVENTORY_PATH, BackgroundServer
from src.inventory_client import InventoryClient, InventoryUnavailable, set_inventory_mode

FRIDAY = date(2026, 11, 6)
SATURDAY = date(2026, 11, 7)
STOCK = {
    row["item_id"]: row["portions"]
    for row in json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))["items"]
}
PIZZA = {"name": "Margherita Pizza", "quantity": 1}
LEMONADE = {"name": "Lemonade", "quantity": 1}
RISOTTO = {"name": "Mushroom Risotto", "quantity": 1}
TWO_SALMON = {"name": "Grilled Salmon", "quantity": 2}
FALAFEL = {"name": "Falafel Wrap", "quantity": 1}


class FakeInventory:
    def __init__(self, portions=None, failure=None):
        self.portions = STOCK if portions is None else portions
        self.failure = failure

    def get_portions(self):
        if self.failure:
            raise InventoryUnavailable(self.failure)
        return self.portions


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.db_path = init_db(Path(tmp_dir.name) / "test.db")
        self.ctx = self.context()

    def context(self, inventory=None, service_date=FRIDAY, db_path=None):
        return ToolContext(
            db_path=db_path or self.db_path,
            inventory=inventory or FakeInventory(),
            service_date=service_date,
            timezone=ZoneInfo("Europe/Berlin"),
        )

    def query(self, sql, params=()):
        with closing(connect(self.db_path, read_only=True)) as conn:
            return [tuple(row) for row in conn.execute(sql, params)]

    def names(self, result):
        self.assertTrue(result["ok"], result)
        return [item["name"] for item in result["items"]]

    def draft_count(self):
        return self.query("SELECT COUNT(*) FROM draft_orders")[0][0]

    def order_item_count(self):
        return self.query("SELECT COUNT(*) FROM order_items")[0][0]

    def assert_error(self, result, code):
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["error"]["code"], code)

    def problem_codes(self, result):
        self.assert_error(result, "draft_refused")
        return {problem["code"] for problem in result["problems"]}

    def assert_refused(self, result, *codes):
        self.assertEqual(self.problem_codes(result), set(codes))
        self.assertEqual(self.draft_count(), 0)
        self.assertEqual(self.order_item_count(), 0)


class SearchMenuTests(ToolTestCase):
    def test_no_filters_returns_the_whole_menu_with_database_prices(self):
        result = tools.search_menu(self.ctx)
        self.assertEqual(
            {(item["name"], item["price_cents"]) for item in result["items"]},
            set(self.query("SELECT name, price_cents FROM menu_items")),
        )

    def test_word_searches_name_and_description_ignoring_case(self):
        self.assertEqual(self.names(tools.search_menu(self.ctx, query="RISOTTO")), ["Mushroom Risotto"])
        self.assertIn("Quinoa Bowl", self.names(tools.search_menu(self.ctx, query="avocado")))

    def test_all_words_must_match_in_any_order(self):
        self.assertEqual(self.names(tools.search_menu(self.ctx, query="curry vegan")), ["Vegan Thai Curry"])

    def test_filters_are_combined(self):
        self.assertEqual(
            self.names(tools.search_menu(self.ctx, category="drink", max_price_eur=3)),
            ["Still Water", "Iced Tea"],
        )

    def test_max_price_is_inclusive(self):
        result = tools.search_menu(self.ctx, query="sorbet", max_price_eur="4.90")
        self.assertEqual(self.names(result), ["Berry Sorbet"])
        self.assertEqual(self.names(tools.search_menu(self.ctx, query="sorbet", max_price_eur=4.89)), [])

    def test_unknown_word_returns_an_empty_list(self):
        self.assertEqual(tools.search_menu(self.ctx, query="sushi"), {"ok": True, "items": []})

    def test_like_wildcards_are_literal(self):
        for query in ("%", "_", "\\"):
            with self.subTest(query):
                self.assertEqual(self.names(tools.search_menu(self.ctx, query=query)), [])

    def test_sql_in_query_is_only_text(self):
        result = tools.search_menu(self.ctx, query="' OR 1=1; DROP TABLE menu_items; --")
        self.assertEqual(self.names(result), [])
        self.assertEqual(self.query("SELECT COUNT(*) FROM menu_items"), [(20,)])

    def test_dish_not_served_today_is_marked(self):
        item = tools.search_menu(self.ctx, query="quinoa")["items"][0]
        self.assertFalse(item["served_today"])

    def test_item_shape(self):
        self.assertEqual(
            tools.search_menu(self.ctx, query="sorbet")["items"][0],
            {
                "name": "Berry Sorbet",
                "category": "dessert",
                "description": "Mixed berry sorbet with lemon.",
                "price_eur": "4.90",
                "price_cents": 490,
                "labels": ["dairy_free", "gluten_free", "vegan", "vegetarian"],
                "allergens": [],
                "served_today": True,
            },
        )

    def test_invalid_arguments_are_refused(self):
        self.assert_error(tools.search_menu(self.ctx, category="mains"), "unknown_category")
        self.assert_error(tools.search_menu(self.ctx, query=5), "invalid_argument")
        self.assert_error(tools.search_menu(self.ctx, max_price_eur="cheap"), "invalid_argument")


class FilterDietaryOptionsTests(ToolTestCase):
    def test_all_labels_are_required(self):
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["vegan", "gluten_free"], category="main"
        )
        self.assertEqual(self.names(result), ["Vegan Thai Curry"])

    def test_labels_are_normalized(self):
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["Vegan", "Gluten-Free"], category="main"
        )
        self.assertEqual(self.names(result), ["Vegan Thai Curry"])

    def test_result_matches_direct_sql(self):
        expected = self.query(
            """
            SELECT m.name FROM menu_items m
            JOIN menu_item_serving_days d ON d.menu_item_id = m.id AND d.weekday = 5
            JOIN menu_item_labels l ON l.menu_item_id = m.id AND l.label_code = 'vegetarian'
            WHERE m.id NOT IN (
              SELECT mi.menu_item_id FROM menu_item_ingredients mi
              JOIN ingredient_allergens ia ON ia.ingredient_id = mi.ingredient_id
              WHERE ia.allergen_code = 'milk')
            ORDER BY m.id
            """
        )
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["vegetarian"], excluded_allergens=["milk"]
        )
        self.assertEqual(self.names(result), [row[0] for row in expected])

    def test_excluded_allergen_removes_dish(self):
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["vegan"], excluded_allergens=["peanuts"], category="main"
        )
        self.assertEqual(self.names(result), ["Falafel Wrap"])

    def test_only_dishes_served_on_the_service_day(self):
        friday = self.names(tools.filter_dietary_options(self.ctx, required_labels=["vegetarian"], category="main"))
        saturday = self.names(
            tools.filter_dietary_options(
                self.context(service_date=SATURDAY), required_labels=["vegetarian"], category="main"
            )
        )
        self.assertNotIn("Spinach Lasagne", friday)
        self.assertIn("Spinach Lasagne", saturday)

    def test_nuts_means_peanuts_and_tree_nuts(self):
        result = tools.filter_dietary_options(self.ctx, excluded_allergens=["nuts"])
        self.assertEqual(result["excluded_allergens"], ["peanuts", "tree_nuts"])
        names = self.names(result)
        self.assertNotIn("Vegan Thai Curry", names)
        self.assertNotIn("Chocolate Brownie", names)

    def test_allergen_aliases(self):
        cases = {
            "Dairy": ["milk"],
            "lactose": ["milk"],
            "egg": ["eggs"],
            "wheat": ["gluten"],
            "Shellfish": ["crustaceans", "molluscs"],
            "soya": ["soy"],
            "sulfites": ["sulphites"],
            "tree nuts": ["tree_nuts"],
        }
        for word, expected in cases.items():
            with self.subTest(word):
                result = tools.filter_dietary_options(self.ctx, excluded_allergens=[word])
                self.assertEqual(result["excluded_allergens"], expected)

    def test_unknown_label_is_refused(self):
        result = tools.filter_dietary_options(self.ctx, required_labels=["keto"])
        self.assert_error(result, "unknown_label")
        self.assertIn("vegan", result["allowed"])
        self.assertIn("keto", result["error"]["message"])

    def test_unknown_allergen_is_refused_not_ignored(self):
        result = tools.filter_dietary_options(self.ctx, excluded_allergens=["peanuts", "sesamee"])
        self.assert_error(result, "unknown_allergen")
        self.assertNotIn("items", result)
        self.assertIn("sesame", result["allowed"])

    def test_max_price(self):
        self.assertEqual(
            self.names(
                tools.filter_dietary_options(
                    self.ctx, required_labels=["vegan"], category="dessert", max_price_eur=4
                )
            ),
            [],
        )

    def test_labels_as_text_are_refused(self):
        self.assert_error(tools.filter_dietary_options(self.ctx, required_labels="vegan"), "invalid_argument")


class GetIngredientsTests(ToolTestCase):
    def test_ingredients_and_allergens_match_the_table(self):
        result = tools.get_ingredients(self.ctx, "Vegan Thai Curry")
        self.assertEqual(result["item"], "Vegan Thai Curry")
        self.assertEqual(result["allergens"], ["peanuts", "soy"])
        self.assertEqual(
            {row["name"]: row["allergens"] for row in result["ingredients"]},
            {
                "Bell pepper": [],
                "Coconut milk": [],
                "Jasmine rice": [],
                "Peanuts": ["peanuts"],
                "Tofu": ["soy"],
            },
        )

    def test_name_ignores_case_and_spaces(self):
        self.assertEqual(tools.get_ingredients(self.ctx, "  vegan thai curry ")["item"], "Vegan Thai Curry")

    def test_ingredient_with_several_allergens(self):
        result = tools.get_ingredients(self.ctx, "Beef Burger")
        bun = next(row for row in result["ingredients"] if row["name"] == "Burger bun")
        self.assertEqual(bun["allergens"], ["gluten", "sesame"])

    def test_unknown_dish_is_not_found(self):
        result = tools.get_ingredients(self.ctx, "Thai Curry")
        self.assert_error(result, "item_not_found")
        self.assertIn("not found", result["error"]["message"])
        self.assertNotIn("allergens", result)


class CheckAvailabilityTests(ToolTestCase):
    def test_reports_portions_from_the_api(self):
        result = tools.check_availability(self.ctx, [PIZZA, RISOTTO])
        self.assertEqual(
            result["items"],
            [
                {"name": "Margherita Pizza", "quantity": 1, "portions_left": 8, "sold_out": False, "available": True},
                {"name": "Mushroom Risotto", "quantity": 1, "portions_left": 0, "sold_out": True, "available": False},
            ],
        )
        self.assertFalse(result["all_available"])

    def test_too_few_portions_are_not_available_but_not_sold_out(self):
        row = tools.check_availability(self.ctx, [{"name": "Spinach Lasagne", "quantity": 4}])["items"][0]
        self.assertEqual((row["sold_out"], row["available"], row["portions_left"]), (False, False, 3))

    def test_all_available(self):
        self.assertTrue(tools.check_availability(self.ctx, [PIZZA, LEMONADE])["all_available"])

    def test_api_failure_gives_an_error_and_no_stock_value(self):
        ctx = self.context(FakeInventory(failure="the inventory service returned HTTP 503"))
        result = tools.check_availability(ctx, [PIZZA])
        self.assert_error(result, "inventory_unavailable")
        self.assertIn("HTTP 503", result["error"]["message"])
        self.assertNotIn("items", result)

    def test_dish_missing_from_the_api_is_not_assumed_available(self):
        ctx = self.context(FakeInventory(portions={17: 5}))
        self.assert_error(tools.check_availability(ctx, [PIZZA]), "inventory_unavailable")

    def test_unknown_dish(self):
        result = tools.check_availability(self.ctx, [{"name": "Sushi", "quantity": 1}])
        self.assert_error(result, "item_not_found")
        self.assertEqual(result["items"], ["Sushi"])


class CalculateTotalTests(ToolTestCase):
    def test_two_salmon_over_a_thirty_euro_budget(self):
        result = tools.calculate_total(self.ctx, [TWO_SALMON], budget_eur=30)
        self.assertTrue(result["ok"])
        self.assertEqual(result["subtotal_eur"], "39.80")
        self.assertEqual(result["subtotal_cents"], 3980)
        self.assertEqual(result["budget_eur"], "30.00")
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["over_budget_by_eur"], "9.80")
        self.assertEqual(result["over_budget_by_cents"], 980)

    def test_total_equals_the_manual_sum_of_database_prices(self):
        names = [row[0] for row in self.query("SELECT name FROM menu_items")]
        prices = self.query("SELECT SUM(price_cents) FROM menu_items")[0][0]
        result = tools.calculate_total(self.ctx, [{"name": name, "quantity": 1} for name in names])
        self.assertEqual(result["subtotal_cents"], prices)

    def test_total_exactly_on_budget_is_within_budget(self):
        result = tools.calculate_total(self.ctx, [PIZZA, LEMONADE], budget_eur="16.00")
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["over_budget_by_eur"], "0.00")

    def test_one_cent_over_is_over_budget(self):
        result = tools.calculate_total(self.ctx, [PIZZA, LEMONADE], budget_eur=15.99)
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["over_budget_by_cents"], 1)

    def test_float_budget_does_not_lose_cents(self):
        # 19.9 * 100 is 1989.9999... as a float, so a float conversion would be wrong here.
        result = tools.calculate_total(self.ctx, [{"name": "Grilled Salmon", "quantity": 1}], budget_eur=19.9)
        self.assertEqual(result["budget_eur"], "19.90")
        self.assertTrue(result["within_budget"])

    def test_no_budget_leaves_budget_fields_empty(self):
        result = tools.calculate_total(self.ctx, [PIZZA])
        for field in ("budget_eur", "within_budget", "over_budget_by_eur", "over_budget_by_cents"):
            self.assertIsNone(result[field])

    def test_line_details(self):
        self.assertEqual(
            tools.calculate_total(self.ctx, [TWO_SALMON])["lines"],
            [
                {
                    "name": "Grilled Salmon",
                    "quantity": 2,
                    "unit_price_eur": "19.90",
                    "unit_price_cents": 1990,
                    "line_total_eur": "39.80",
                    "line_total_cents": 3980,
                }
            ],
        )

    def test_repeated_dish_is_merged(self):
        result = tools.calculate_total(
            self.ctx, [PIZZA, {"name": "margherita pizza", "quantity": 2}]
        )
        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["subtotal_cents"], 3750)

    def test_invalid_lines_are_refused(self):
        bad_items = {
            "empty": [],
            "not a list": "Lemonade",
            "not a dict": ["Lemonade"],
            "no name": [{"quantity": 1}],
            "blank name": [{"name": " ", "quantity": 1}],
            "no quantity": [{"name": "Lemonade"}],
            "zero": [{"name": "Lemonade", "quantity": 0}],
            "negative": [{"name": "Lemonade", "quantity": -1}],
            "fraction": [{"name": "Lemonade", "quantity": 1.5}],
            "boolean": [{"name": "Lemonade", "quantity": True}],
            "text": [{"name": "Lemonade", "quantity": "2"}],
            "too many": [{"name": "Lemonade", "quantity": 21}],
            "too many merged": [{"name": "Lemonade", "quantity": 15}, {"name": "lemonade", "quantity": 6}],
        }
        for name, items in bad_items.items():
            with self.subTest(name):
                self.assert_error(tools.calculate_total(self.ctx, items), "invalid_argument")

    def test_invalid_budgets_are_refused(self):
        for budget in (-1, "abc", "NaN", "Infinity", True, 1.234, [20], 1e30):
            with self.subTest(budget):
                self.assert_error(tools.calculate_total(self.ctx, [PIZZA], budget_eur=budget), "invalid_argument")

    def test_unknown_dish_gives_no_total(self):
        result = tools.calculate_total(self.ctx, [PIZZA, {"name": "Sushi", "quantity": 1}])
        self.assert_error(result, "item_not_found")
        self.assertNotIn("subtotal_cents", result)


class DraftOrderTests(ToolTestCase):
    def valid_draft(self, **overrides):
        arguments = {
            "items": [PIZZA, LEMONADE],
            "pickup_time": "18:30",
            "required_labels": ["vegetarian"],
            "budget_eur": 20,
            **overrides,
        }
        return tools.draft_order(self.ctx, **arguments)

    def test_valid_draft_is_saved_and_awaits_confirmation(self):
        result = self.valid_draft()
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["already_existed"])
        draft = result["draft"]
        self.assertEqual(draft["status"], "awaiting_customer_confirmation")
        self.assertEqual(draft["subtotal_eur"], "16.00")
        self.assertEqual(
            self.query(
                "SELECT status, service_date, pickup_time, budget_cents, required_labels,"
                " excluded_allergens, subtotal_cents FROM draft_orders"
            ),
            [("awaiting_customer_confirmation", "2026-11-06", "18:30", 2000, '["vegetarian"]', "[]", 1600)],
        )
        self.assertEqual(
            self.query(
                "SELECT m.name, o.quantity, o.unit_price_cents FROM order_items o"
                " JOIN menu_items m ON m.id = o.menu_item_id WHERE o.draft_order_id = ? ORDER BY m.id",
                (draft["draft_id"],),
            ),
            [("Margherita Pizza", 1, 1250), ("Lemonade", 1, 350)],
        )

    def test_stored_subtotal_equals_the_database_prices(self):
        self.valid_draft()
        self.assertEqual(
            self.query(
                "SELECT d.subtotal_cents, SUM(m.price_cents * o.quantity) FROM draft_orders d"
                " JOIN order_items o ON o.draft_order_id = d.id"
                " JOIN menu_items m ON m.id = o.menu_item_id GROUP BY d.id"
            ),
            [(1600, 1600)],
        )

    def test_budget_and_labels_are_optional(self):
        self.assertTrue(tools.draft_order(self.ctx, [PIZZA], "12:00")["ok"])

    def test_pickup_hour_boundaries_are_included(self):
        self.assertTrue(self.valid_draft(pickup_time="11:00")["ok"])
        self.assertTrue(self.valid_draft(pickup_time="21:00")["ok"])

    def test_outside_pickup_hours(self):
        for pickup_time in ("10:59", "21:01", "23:30", "00:00"):
            with self.subTest(pickup_time):
                self.assert_refused(self.valid_draft(pickup_time=pickup_time), "outside_pickup_hours")

    def test_invalid_pickup_time(self):
        for pickup_time in ("18.30", "6pm", "9:30", "24:00", "18:60", "", None, 1830, "18:30:00"):
            with self.subTest(pickup_time):
                self.assert_refused(self.valid_draft(pickup_time=pickup_time), "invalid_pickup_time")

    def test_unknown_dish(self):
        result = self.valid_draft(items=[{"name": "Sushi", "quantity": 1}])
        self.assert_refused(result, "item_not_found")
        self.assertEqual(result["problems"][0]["item"], "Sushi")

    def test_dish_not_served_today(self):
        self.assert_refused(
            self.valid_draft(items=[{"name": "Spinach Lasagne", "quantity": 1}]), "not_served_today"
        )

    def test_dish_without_required_label(self):
        result = self.valid_draft(items=[{"name": "Grilled Salmon", "quantity": 1}])
        self.assert_refused(result, "missing_label")
        self.assertEqual(result["problems"][0]["labels"], ["vegetarian"])

    def test_dish_with_excluded_allergen(self):
        result = tools.draft_order(
            self.ctx,
            [{"name": "Vegan Thai Curry", "quantity": 1}],
            "18:00",
            excluded_allergens=["nuts"],
        )
        self.assert_refused(result, "contains_allergen")
        self.assertEqual(result["problems"][0]["allergens"], ["peanuts"])

    def test_over_budget(self):
        result = tools.draft_order(self.ctx, [TWO_SALMON], "18:00", budget_eur=30)
        self.assert_refused(result, "over_budget")
        self.assertEqual(result["problems"][0]["over_budget_by_eur"], "9.80")

    def test_exactly_on_budget_is_saved(self):
        self.assertTrue(self.valid_draft(budget_eur=16)["ok"])

    def test_sold_out(self):
        self.assert_refused(tools.draft_order(self.ctx, [RISOTTO], "19:00"), "sold_out")

    def test_insufficient_stock(self):
        ctx = self.context(FakeInventory(portions={1: 1, 17: 5}))
        result = tools.draft_order(ctx, [{"name": "Margherita Pizza", "quantity": 2}], "19:00")
        self.assert_refused(result, "insufficient_stock")
        self.assertEqual(result["problems"][0]["portions_left"], 1)

    def test_api_failure_fails_closed(self):
        ctx = self.context(FakeInventory(failure="the inventory service returned HTTP 503"))
        self.assert_refused(tools.draft_order(ctx, [PIZZA], "18:30"), "inventory_unavailable")

    def test_dish_missing_from_the_api_fails_closed(self):
        ctx = self.context(FakeInventory(portions={17: 5}))
        self.assert_refused(tools.draft_order(ctx, [PIZZA], "18:30"), "inventory_unavailable")

    def test_all_problems_are_reported_together(self):
        ctx = self.context(FakeInventory(portions={2: 0, 5: 1, 9: 3}))
        result = tools.draft_order(
            ctx,
            [
                RISOTTO,
                TWO_SALMON,
                {"name": "Spinach Lasagne", "quantity": 1},
                {"name": "Sushi", "quantity": 1},
            ],
            "23:30",
            required_labels=["vegan"],
            excluded_allergens=["milk"],
        )
        self.assert_refused(
            result,
            "outside_pickup_hours",
            "item_not_found",
            "not_served_today",
            "missing_label",
            "contains_allergen",
            "sold_out",
            "insufficient_stock",
        )

    def test_over_budget_is_reported_with_other_problems(self):
        result = tools.draft_order(self.ctx, [TWO_SALMON, RISOTTO], "23:30", budget_eur=30)
        self.assert_refused(result, "outside_pickup_hours", "over_budget", "sold_out")

    def test_unknown_values_are_refused_before_saving(self):
        self.assert_error(self.valid_draft(required_labels=["keto"]), "unknown_label")
        self.assert_error(self.valid_draft(excluded_allergens=["sesamee"]), "unknown_allergen")
        self.assert_error(self.valid_draft(budget_eur="abc"), "invalid_argument")
        self.assert_error(self.valid_draft(items=[]), "invalid_argument")
        self.assertEqual(self.draft_count(), 0)

    def test_identical_retry_returns_the_same_draft(self):
        first = self.valid_draft()
        second = self.valid_draft(items=[LEMONADE, PIZZA])
        self.assertEqual(second["draft"]["draft_id"], first["draft"]["draft_id"])
        self.assertTrue(second["already_existed"])
        self.assertEqual(self.draft_count(), 1)
        self.assertEqual(self.order_item_count(), 2)

    def test_different_content_creates_a_new_draft(self):
        self.valid_draft()
        changes = (
            {"pickup_time": "18:45"},
            {"budget_eur": 25},
            {"required_labels": []},
            {"excluded_allergens": ["fish"]},
            {"items": [{"name": "Margherita Pizza", "quantity": 1}]},
            {"items": [{"name": "Margherita Pizza", "quantity": 2}, LEMONADE], "budget_eur": 30},
        )
        for number, overrides in enumerate(changes, start=2):
            with self.subTest(overrides):
                self.assertFalse(self.valid_draft(**overrides)["already_existed"])
                self.assertEqual(self.draft_count(), number)

    def test_different_dishes_with_the_same_total_create_a_new_draft(self):
        soup = tools.draft_order(self.ctx, [{"name": "Tomato Soup", "quantity": 1}], "18:00")
        tiramisu = tools.draft_order(self.ctx, [{"name": "Tiramisu", "quantity": 1}], "18:00")
        self.assertEqual(soup["draft"]["subtotal_cents"], tiramisu["draft"]["subtotal_cents"])
        self.assertFalse(tiramisu["already_existed"])
        self.assertEqual(self.draft_count(), 2)

    def test_confirmed_draft_is_not_reused(self):
        first = self.valid_draft()
        with closing(connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE draft_orders SET status = 'confirmed'")
        second = self.valid_draft()
        self.assertNotEqual(second["draft"]["draft_id"], first["draft"]["draft_id"])

    def test_failed_item_insert_rolls_back_the_draft(self):
        with closing(connect(self.db_path)) as conn, conn:
            conn.execute(
                "CREATE TRIGGER fail_order_items BEFORE INSERT ON order_items"
                " BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
            )
        self.assert_error(self.valid_draft(), "database_error")
        self.assertEqual(self.draft_count(), 0)

    def test_no_tool_can_set_another_status(self):
        self.valid_draft()
        self.assertEqual(self.query("SELECT DISTINCT status FROM draft_orders"), [("awaiting_customer_confirmation",)])


class RobustnessTests(ToolTestCase):
    def test_every_tool_reports_a_missing_database_as_an_error(self):
        ctx = self.context(db_path=self.db_path.with_name("missing.db"))
        calls = (
            lambda: tools.search_menu(ctx),
            lambda: tools.filter_dietary_options(ctx),
            lambda: tools.get_ingredients(ctx, "Lemonade"),
            lambda: tools.check_availability(ctx, [LEMONADE]),
            lambda: tools.calculate_total(ctx, [LEMONADE]),
            lambda: tools.draft_order(ctx, [LEMONADE], "18:00"),
        )
        for call in calls:
            self.assert_error(call(), "database_error")

    def test_all_results_are_json_serializable(self):
        results = (
            tools.search_menu(self.ctx),
            tools.filter_dietary_options(self.ctx, required_labels=["vegan"]),
            tools.get_ingredients(self.ctx, "Lemonade"),
            tools.check_availability(self.ctx, [LEMONADE]),
            tools.calculate_total(self.ctx, [LEMONADE], budget_eur=5),
            tools.draft_order(self.ctx, [LEMONADE], "18:00", budget_eur=5),
            tools.draft_order(self.ctx, [RISOTTO], "23:30"),
        )
        for result in results:
            json.dumps(result)

    def test_read_tools_do_not_write(self):
        before = self.query("SELECT COUNT(*) FROM draft_orders")
        tools.search_menu(self.ctx)
        tools.filter_dietary_options(self.ctx)
        tools.get_ingredients(self.ctx, "Lemonade")
        tools.check_availability(self.ctx, [LEMONADE])
        tools.calculate_total(self.ctx, [LEMONADE])
        self.assertEqual(self.query("SELECT COUNT(*) FROM draft_orders"), before)

    def test_tools_tuple_has_the_six_approved_tools(self):
        self.assertEqual(
            [tool.__name__ for tool in tools.TOOLS],
            [
                "search_menu",
                "filter_dietary_options",
                "get_ingredients",
                "check_availability",
                "calculate_total",
                "draft_order",
            ],
        )


class EvaluationScenarioTests(ToolTestCase):
    """E-01 to E-08 through the tools and a real HTTP server, without a model."""

    def setUp(self):
        super().setUp()
        self.server = BackgroundServer().start()
        self.addCleanup(self.server.stop)
        self.ctx = self.context(InventoryClient(self.server.url, timeout=1.0))

    def test_e01_normal_task(self):
        options = tools.filter_dietary_options(self.ctx, required_labels=["vegetarian"])
        self.assertIn("Margherita Pizza", self.names(options))
        self.assertTrue(tools.check_availability(self.ctx, [PIZZA, LEMONADE])["all_available"])

        result = tools.draft_order(
            self.ctx, [PIZZA, LEMONADE], "18:30", required_labels=["vegetarian"], budget_eur=20
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["draft"]["subtotal_eur"], "16.00")
        self.assertEqual(self.draft_count(), 1)

    def test_e01_sold_out_dish_cannot_be_drafted(self):
        result = tools.draft_order(
            self.ctx, [RISOTTO, LEMONADE], "18:30", required_labels=["vegetarian"], budget_eur=20
        )
        self.assert_refused(result, "sold_out")

    def test_e02_database_filter(self):
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["vegan", "gluten_free"], category="main"
        )
        self.assertEqual(self.names(result), ["Vegan Thai Curry"])

    def test_e03_allergen_safety(self):
        result = tools.get_ingredients(self.ctx, "Vegan Thai Curry")
        self.assertEqual(result["allergens"], ["peanuts", "soy"])

    def test_e04_sold_out(self):
        availability = tools.check_availability(self.ctx, [RISOTTO])
        self.assertTrue(availability["items"][0]["sold_out"])
        self.assert_refused(tools.draft_order(self.ctx, [RISOTTO], "19:00"), "sold_out")

    def test_e05_no_match(self):
        result = tools.filter_dietary_options(
            self.ctx, required_labels=["vegan"], category="dessert", max_price_eur=4
        )
        self.assertEqual(self.names(result), [])
        cheapest = tools.filter_dietary_options(self.ctx, required_labels=["vegan"], category="dessert")
        self.assertEqual(
            [(item["name"], item["price_eur"]) for item in cheapest["items"]], [("Berry Sorbet", "4.90")]
        )

    def test_e06_api_failure(self):
        set_inventory_mode(self.server.url, "outage")
        availability = tools.check_availability(self.ctx, [PIZZA])
        self.assert_error(availability, "inventory_unavailable")
        self.assertIn("HTTP 503", availability["error"]["message"])
        self.assert_refused(tools.draft_order(self.ctx, [PIZZA], "18:30"), "inventory_unavailable")

    def test_e07_budget_overrun(self):
        total = tools.calculate_total(self.ctx, [TWO_SALMON], budget_eur=30)
        self.assertEqual(total["subtotal_eur"], "39.80")
        self.assertEqual(total["over_budget_by_eur"], "9.80")
        self.assert_refused(tools.draft_order(self.ctx, [TWO_SALMON], "18:00", budget_eur=30), "over_budget")

    def test_e08_invalid_pickup_time(self):
        result = tools.draft_order(self.ctx, [FALAFEL], "23:30")
        self.assert_refused(result, "outside_pickup_hours")
        self.assertIn("11:00-21:00", result["problems"][0]["message"])


if __name__ == "__main__":
    unittest.main()
