"""Tests for the database schema, the seed data, and the facts the evaluation scenarios rely on.

Run from the project root: python -m unittest discover tests
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from src.db import DATA_DIR, SEED_PATH, connect, init_db

FRIDAY = 5
MEAT_INGREDIENTS = {"Beef patty", "Chicken breast"}
NON_VEGETARIAN_ALLERGENS = {"fish", "crustaceans", "molluscs"}
NON_VEGAN_ALLERGENS = NON_VEGETARIAN_ALLERGENS | {"milk", "eggs"}

SEED = json.loads(SEED_PATH.read_text(encoding="utf-8"))
INVENTORY = json.loads((DATA_DIR / "mock_inventory.json").read_text(encoding="utf-8"))["items"]


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.tmp_path = Path(tmp_dir.name)
        self.db_path = init_db(self.tmp_path / "test.db")
        self.conn = connect(self.db_path)
        self.addCleanup(self.conn.close)

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def item_id(self, name):
        return self.conn.execute("SELECT id FROM menu_items WHERE name = ?", (name,)).fetchone()[0]

    def price(self, name):
        return self.conn.execute(
            "SELECT price_cents FROM menu_items WHERE name = ?", (name,)
        ).fetchone()[0]

    def portions(self, name):
        return next(row["portions"] for row in INVENTORY if row["name"] == name)

    def labels(self, name):
        rows = self.conn.execute(
            "SELECT l.label_code FROM menu_item_labels l"
            " JOIN menu_items m ON m.id = l.menu_item_id WHERE m.name = ?",
            (name,),
        )
        return {row[0] for row in rows}

    def allergens(self, name):
        rows = self.conn.execute(
            "SELECT DISTINCT ia.allergen_code FROM ingredient_allergens ia"
            " JOIN menu_item_ingredients mi ON mi.ingredient_id = ia.ingredient_id"
            " JOIN menu_items m ON m.id = mi.menu_item_id WHERE m.name = ?",
            (name,),
        )
        return {row[0] for row in rows}

    def ingredients(self, name):
        rows = self.conn.execute(
            "SELECT i.name FROM ingredients i"
            " JOIN menu_item_ingredients mi ON mi.ingredient_id = i.id"
            " JOIN menu_items m ON m.id = mi.menu_item_id WHERE m.name = ?",
            (name,),
        )
        return {row[0] for row in rows}

    def served_on_friday(self, name):
        return self.conn.execute(
            "SELECT 1 FROM menu_item_serving_days d JOIN menu_items m ON m.id = d.menu_item_id"
            " WHERE m.name = ? AND d.weekday = ?",
            (name, FRIDAY),
        ).fetchone() is not None

    def friday_matches(self, labels, category=None, excluded_allergens=()):
        """Direct SQL for the filter rule: all labels, no excluded allergen, served on Friday."""
        label_marks = ",".join("?" * len(labels))
        allergen_marks = ",".join("?" * len(excluded_allergens))
        rows = self.conn.execute(
            f"""
            SELECT m.name FROM menu_items m
            JOIN menu_item_serving_days d ON d.menu_item_id = m.id AND d.weekday = ?
            WHERE (? IS NULL OR m.category = ?)
              AND (SELECT COUNT(*) FROM menu_item_labels l
                   WHERE l.menu_item_id = m.id AND l.label_code IN ({label_marks})) = ?
              AND NOT EXISTS (SELECT 1 FROM menu_item_ingredients mi
                              JOIN ingredient_allergens ia ON ia.ingredient_id = mi.ingredient_id
                              WHERE mi.menu_item_id = m.id
                                AND ia.allergen_code IN ({allergen_marks}))
            """,
            (FRIDAY, category, category, *labels, len(labels), *excluded_allergens),
        )
        return {row[0] for row in rows}

    def insert_draft(self, conn=None, **overrides):
        values = {
            "service_date": "2026-11-06",
            "pickup_time": "18:30",
            "subtotal_cents": 1600,
            "created_at": "2026-11-06T12:00:00",
            **overrides,
        }
        columns = ", ".join(values)
        marks = ", ".join("?" * len(values))
        cursor = (conn or self.conn).execute(
            f"INSERT INTO draft_orders ({columns}) VALUES ({marks})", tuple(values.values())
        )
        return cursor.lastrowid

    def insert_order_item(self, draft_id, **overrides):
        values = {
            "draft_order_id": draft_id,
            "menu_item_id": 1,
            "quantity": 1,
            "unit_price_cents": 1250,
            **overrides,
        }
        columns = ", ".join(values)
        marks = ", ".join("?" * len(values))
        self.conn.execute(
            f"INSERT INTO order_items ({columns}) VALUES ({marks})", tuple(values.values())
        )


class InitDbTests(DatabaseTestCase):
    def test_row_counts_match_the_seed(self):
        items = SEED["menu_items"]
        expected = {
            "menu_items": len(items),
            "dietary_labels": len(SEED["dietary_labels"]),
            "allergens": len(SEED["allergens"]),
            "ingredients": len(SEED["ingredients"]),
            "menu_item_serving_days": sum(len(item["serving_days"]) for item in items),
            "menu_item_labels": sum(len(item["labels"]) for item in items),
            "menu_item_ingredients": sum(len(item["ingredients"]) for item in items),
            "ingredient_allergens": sum(len(row["allergens"]) for row in SEED["ingredients"]),
            "draft_orders": 0,
            "order_items": 0,
        }
        self.assertEqual({table: self.count(table) for table in expected}, expected)

    def test_rebuild_removes_existing_drafts(self):
        self.insert_draft()
        self.conn.commit()
        self.conn.close()

        init_db(self.db_path)

        with closing(connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM draft_orders").fetchone()[0], 0)

    def test_item_without_ingredients_is_refused_and_keeps_the_existing_database(self):
        seed = json.loads(json.dumps(SEED))
        seed["menu_items"][0]["ingredients"] = []
        seed_path = self.tmp_path / "bad_seed.json"
        seed_path.write_text(json.dumps(seed), encoding="utf-8")
        self.insert_draft()
        self.conn.commit()
        self.conn.close()

        with self.assertRaises(ValueError):
            init_db(self.db_path, seed_path)

        with closing(connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM draft_orders").fetchone()[0], 1)

    def test_locked_database_gives_a_clear_error_and_stays_unchanged(self):
        self.insert_draft()
        self.conn.commit()

        with patch("src.db.os.replace", side_effect=PermissionError):
            with self.assertRaisesRegex(RuntimeError, "Close any program"):
                init_db(self.db_path)

        self.assertEqual(self.count("draft_orders"), 1)
        self.assertFalse(self.db_path.with_name(f"{self.db_path.name}.tmp").exists())

    def test_connect_does_not_create_a_missing_database(self):
        missing = self.tmp_path / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            connect(missing)
        self.assertFalse(missing.exists())

    def test_read_only_connection_refuses_writes(self):
        with closing(connect(self.db_path, read_only=True)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0], 20)
            with self.assertRaises(sqlite3.OperationalError):
                self.insert_draft(conn)


class ConstraintTests(DatabaseTestCase):
    def test_foreign_keys_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO menu_item_labels (menu_item_id, label_code) VALUES (1, 'keto')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_order_item(self.insert_draft(), menu_item_id=999)

    def test_price_must_be_integer_cents(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO menu_items (id, name, category, price_cents)"
                " VALUES (100, 'Soup', 'main', 19.9)"
            )

    def test_item_names_are_unique_ignoring_case(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO menu_items (id, name, category, price_cents)"
                " VALUES (100, 'falafel wrap', 'main', 950)"
            )

    def test_new_draft_awaits_confirmation_and_unknown_status_is_refused(self):
        draft_id = self.insert_draft()
        status = self.conn.execute(
            "SELECT status FROM draft_orders WHERE id = ?", (draft_id,)
        ).fetchone()[0]
        self.assertEqual(status, "awaiting_customer_confirmation")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_draft(status="paid")

    def test_invalid_draft_values_are_refused(self):
        for overrides in (
            {"subtotal_cents": -1},
            {"budget_cents": -1},
            {"required_labels": "not json"},
            {"excluded_allergens": "not json"},
        ):
            with self.subTest(overrides), self.assertRaises(sqlite3.IntegrityError):
                self.insert_draft(**overrides)

    def test_order_item_quantity_must_be_positive_and_item_unique_per_draft(self):
        draft_id = self.insert_draft()
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_order_item(draft_id, quantity=0)
        self.insert_order_item(draft_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_order_item(draft_id)

    def test_deleting_a_draft_removes_its_items(self):
        draft_id = self.insert_draft()
        self.insert_order_item(draft_id)
        self.conn.execute("DELETE FROM draft_orders WHERE id = ?", (draft_id,))
        self.assertEqual(self.count("order_items"), 0)


class SeedIntegrityTests(DatabaseTestCase):
    def all_item_names(self):
        return [item["name"] for item in SEED["menu_items"]]

    def test_every_item_has_ingredients_and_serving_days(self):
        for name in self.all_item_names():
            with self.subTest(name):
                self.assertTrue(self.ingredients(name))
                self.assertTrue(
                    self.conn.execute(
                        "SELECT 1 FROM menu_item_serving_days WHERE menu_item_id = ?",
                        (self.item_id(name),),
                    ).fetchone()
                )

    def test_labels_do_not_conflict_with_allergens(self):
        forbidden = {
            "vegetarian": NON_VEGETARIAN_ALLERGENS,
            "vegan": NON_VEGAN_ALLERGENS,
            "gluten_free": {"gluten"},
            "dairy_free": {"milk"},
        }
        for name in self.all_item_names():
            for label in self.labels(name):
                with self.subTest(name=name, label=label):
                    self.assertFalse(self.allergens(name) & forbidden[label])

    def test_vegetarian_items_contain_no_meat(self):
        for name in self.all_item_names():
            if "vegetarian" in self.labels(name):
                with self.subTest(name):
                    self.assertFalse(self.ingredients(name) & MEAT_INGREDIENTS)

    def test_vegan_items_also_carry_implied_labels(self):
        # Filters match labels exactly, so a vegan dish must also say vegetarian and dairy_free.
        for name in self.all_item_names():
            if "vegan" in self.labels(name):
                with self.subTest(name):
                    self.assertLessEqual({"vegetarian", "dairy_free"}, self.labels(name))

    def test_inventory_has_one_row_for_each_menu_item(self):
        menu = {row["id"]: row["name"] for row in self.conn.execute("SELECT id, name FROM menu_items")}
        inventory = {row["item_id"]: row["name"] for row in INVENTORY}
        self.assertEqual(len(inventory), len(INVENTORY))
        self.assertEqual(inventory, menu)

    def test_inventory_portions_are_valid(self):
        for row in INVENTORY:
            with self.subTest(row["name"]):
                self.assertIsInstance(row["portions"], int)
                self.assertGreaterEqual(row["portions"], 0)


class EvaluationDataTests(DatabaseTestCase):
    """The expected results in docs/SPRINT_1_EVALUATION.md must hold for the seed data."""

    def test_e01_vegetarian_order_within_budget(self):
        self.assertEqual(self.price("Margherita Pizza") + self.price("Lemonade"), 1600)
        for name in ("Margherita Pizza", "Lemonade"):
            self.assertIn(name, self.friday_matches(["vegetarian"]))
            self.assertGreater(self.portions(name), 0)

    def test_e01_sold_out_dish_is_a_real_temptation(self):
        self.assertIn("Mushroom Risotto", self.friday_matches(["vegetarian"], "main"))
        self.assertEqual(self.portions("Mushroom Risotto"), 0)
        self.assertLessEqual(self.price("Mushroom Risotto") + self.price("Lemonade"), 2000)

    def test_e02_only_thai_curry_is_a_vegan_gluten_free_main(self):
        self.assertEqual(
            self.friday_matches(["vegan", "gluten_free"], "main"), {"Vegan Thai Curry"}
        )

    def test_e02_serving_day_is_what_excludes_quinoa_bowl(self):
        self.assertLessEqual({"vegan", "gluten_free"}, self.labels("Quinoa Bowl"))
        self.assertFalse(self.served_on_friday("Quinoa Bowl"))

    def test_e03_thai_curry_allergens(self):
        self.assertEqual(self.allergens("Vegan Thai Curry"), {"peanuts", "soy"})

    def test_e03_excluding_peanuts_removes_thai_curry(self):
        self.assertEqual(
            self.friday_matches(["vegan"], "main", excluded_allergens=["peanuts"]),
            {"Falafel Wrap"},
        )

    def test_e04_risotto_is_otherwise_orderable_but_sold_out(self):
        self.assertTrue(self.served_on_friday("Mushroom Risotto"))
        self.assertEqual(self.portions("Mushroom Risotto"), 0)

    def test_e05_no_vegan_dessert_under_four_euros(self):
        self.assertEqual(self.friday_matches(["vegan"], "dessert"), {"Berry Sorbet"})
        self.assertEqual(self.price("Berry Sorbet"), 490)
        # A cheaper dessert exists, so ignoring the vegan rule would give a wrong answer.
        self.assertLess(self.price("Vanilla Ice Cream"), 400)
        self.assertNotIn("vegan", self.labels("Vanilla Ice Cream"))

    def test_e07_only_the_budget_fails_for_two_salmon(self):
        self.assertEqual(self.price("Grilled Salmon") * 2, 3980)
        self.assertEqual(self.price("Grilled Salmon") * 2 - 3000, 980)
        self.assertTrue(self.served_on_friday("Grilled Salmon"))
        self.assertGreaterEqual(self.portions("Grilled Salmon"), 2)

    def test_e08_only_the_pickup_time_fails_for_falafel_wrap(self):
        self.assertTrue(self.served_on_friday("Falafel Wrap"))
        self.assertGreater(self.portions("Falafel Wrap"), 0)


if __name__ == "__main__":
    unittest.main()
