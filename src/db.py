"""SQLite connections and database creation for the restaurant data."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHEMA_PATH = DATA_DIR / "schema.sql"
SEED_PATH = DATA_DIR / "seed.json"
DB_PATH = DATA_DIR / "restaurant.db"

MIN_SQLITE_VERSION = (3, 37, 0)  # First version with STRICT tables.


def _open(db_path, mode):
    uri = f"{Path(db_path).resolve().as_uri()}?mode={mode}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless each connection asks for it.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect(db_path=DB_PATH, *, read_only=False):
    """Open an existing database. A missing file raises an error instead of creating an empty one."""
    return _open(db_path, "ro" if read_only else "rw")


def _insert_seed(conn, seed):
    conn.executemany(
        "INSERT INTO dietary_labels (code) VALUES (?)",
        [(code,) for code in seed["dietary_labels"]],
    )
    conn.executemany(
        "INSERT INTO allergens (code) VALUES (?)",
        [(code,) for code in seed["allergens"]],
    )

    ingredient_ids = {}
    for ingredient in seed["ingredients"]:
        cursor = conn.execute(
            "INSERT INTO ingredients (name) VALUES (?)", (ingredient["name"],)
        )
        ingredient_ids[ingredient["name"]] = cursor.lastrowid
        conn.executemany(
            "INSERT INTO ingredient_allergens (ingredient_id, allergen_code) VALUES (?, ?)",
            [(cursor.lastrowid, code) for code in ingredient["allergens"]],
        )

    for item in seed["menu_items"]:
        # A dish without ingredients would pass every allergen filter as if it were safe.
        if not item["ingredients"] or not item["serving_days"]:
            raise ValueError(f"{item['name']} needs ingredients and serving days")
        unknown = set(item["ingredients"]) - ingredient_ids.keys()
        if unknown:
            raise ValueError(f"{item['name']} uses unknown ingredients: {sorted(unknown)}")

        conn.execute(
            "INSERT INTO menu_items (id, name, category, description, price_cents)"
            " VALUES (?, ?, ?, ?, ?)",
            (item["id"], item["name"], item["category"], item["description"], item["price_cents"]),
        )
        conn.executemany(
            "INSERT INTO menu_item_serving_days (menu_item_id, weekday) VALUES (?, ?)",
            [(item["id"], weekday) for weekday in item["serving_days"]],
        )
        conn.executemany(
            "INSERT INTO menu_item_labels (menu_item_id, label_code) VALUES (?, ?)",
            [(item["id"], code) for code in item["labels"]],
        )
        conn.executemany(
            "INSERT INTO menu_item_ingredients (menu_item_id, ingredient_id) VALUES (?, ?)",
            [(item["id"], ingredient_ids[name]) for name in item["ingredients"]],
        )


def init_db(db_path=DB_PATH, seed_path=SEED_PATH):
    """Build a fresh database from the schema and seed, replacing any existing file and its drafts."""
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise RuntimeError(f"SQLite 3.37+ is required, found {sqlite3.sqlite_version}")

    db_path = Path(db_path)
    seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    # Build beside the target so that a bad seed leaves the existing database untouched.
    tmp_path = db_path.with_name(f"{db_path.name}.tmp")
    tmp_path.unlink(missing_ok=True)
    try:
        with closing(_open(tmp_path, "rwc")) as conn:
            conn.executescript(schema)
            with conn:
                _insert_seed(conn, seed)
        try:
            os.replace(tmp_path, db_path)
        except PermissionError as exc:
            raise RuntimeError(
                f"Cannot replace {db_path}. Close any program that has it open, such as"
                " DB Browser for SQLite, and try again."
            ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return db_path


if __name__ == "__main__":
    print(f"Created {init_db()}")
