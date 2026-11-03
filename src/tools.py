"""The six restaurant tools. See docs/CONTRACT.md for arguments and return values.

Every fact comes from the database or the inventory API. Tools never raise to the caller.
"""

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from functools import wraps

from src.db import connect
from src.inventory_client import InventoryUnavailable

CATEGORIES = ("starter", "main", "dessert", "drink")
DRAFT_STATUS = "awaiting_customer_confirmation"
MAX_QUANTITY_PER_ITEM = 20
MAX_AMOUNT_CENTS = 100_000_000

# Words customers use for allergens. An ambiguous word expands to everything it can mean.
ALLERGEN_ALIASES = {
    "nut": ("peanuts", "tree_nuts"),
    "nuts": ("peanuts", "tree_nuts"),
    "peanut": ("peanuts",),
    "tree_nut": ("tree_nuts",),
    "shellfish": ("crustaceans", "molluscs"),
    "crustacean": ("crustaceans",),
    "mollusc": ("molluscs",),
    "mollusk": ("molluscs",),
    "mollusks": ("molluscs",),
    "dairy": ("milk",),
    "lactose": ("milk",),
    "egg": ("eggs",),
    "wheat": ("gluten",),
    "soya": ("soy",),
    "soybean": ("soy",),
    "soybeans": ("soy",),
    "sulphite": ("sulphites",),
    "sulfite": ("sulphites",),
    "sulfites": ("sulphites",),
}

ITEM_COLUMNS = "m.id, m.name, m.category, m.description, m.price_cents"


class ToolError(Exception):
    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def _error(code, message, **extra):
    return {"ok": False, "error": {"code": code, "message": message}, **extra}


def _tool(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ToolError as exc:
            return _error(exc.code, exc.message, **exc.extra)
        except sqlite3.Error:
            return _error("database_error", "The restaurant database could not be read or updated.")

    return wrapper


def _format_eur(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def _to_cents(amount, name):
    if amount is None:
        return None
    if isinstance(amount, bool) or not isinstance(amount, (int, float, str, Decimal)):
        raise ToolError("invalid_argument", f"{name} must be a number of euros.")
    try:
        cents = Decimal(str(amount).strip()) * 100
    except InvalidOperation:
        raise ToolError("invalid_argument", f"{name} must be a number of euros.") from None
    if not cents.is_finite() or cents != cents.to_integral_value():
        raise ToolError("invalid_argument", f"{name} must have at most 2 decimal places.")
    if not 0 <= cents <= MAX_AMOUNT_CENTS:
        raise ToolError("invalid_argument", f"{name} is out of range.")
    return int(cents)


def _normalize_code(value, name):
    if not isinstance(value, str):
        raise ToolError("invalid_argument", f"{name} must contain text values.")
    return re.sub(r"[\s-]+", "_", value.strip().lower())


def _resolve_codes(conn, values, table, aliases, error_code, name):
    """Map input words to known codes. An unknown word is refused, never ignored."""
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise ToolError("invalid_argument", f"{name} must be a list.")
    known = {row["code"] for row in conn.execute(f"SELECT code FROM {table}")}
    resolved = set()
    unknown = []
    for value in values:
        code = _normalize_code(value, name)
        codes = aliases.get(code, (code,))
        if set(codes) <= known:
            resolved.update(codes)
        else:
            unknown.append(value)
    if unknown:
        raise ToolError(
            error_code,
            f"Unknown value in {name}: {', '.join(unknown)}. This value cannot be checked.",
            allowed=sorted(known),
        )
    return sorted(resolved)


def _resolve_labels(conn, labels):
    return _resolve_codes(conn, labels, "dietary_labels", {}, "unknown_label", "required_labels")


def _resolve_allergens(conn, allergens):
    return _resolve_codes(
        conn, allergens, "allergens", ALLERGEN_ALIASES, "unknown_allergen", "excluded_allergens"
    )


def _resolve_category(category):
    if category is None:
        return None
    code = _normalize_code(category, "category")
    if code not in CATEGORIES:
        raise ToolError(
            "unknown_category", f"Unknown category: {category}.", allowed=list(CATEGORIES)
        )
    return code


def _labels_of(conn, item_id):
    rows = conn.execute(
        "SELECT label_code FROM menu_item_labels WHERE menu_item_id = ? ORDER BY label_code",
        (item_id,),
    )
    return [row["label_code"] for row in rows]


def _allergens_of(conn, item_id):
    rows = conn.execute(
        "SELECT DISTINCT ia.allergen_code FROM menu_item_ingredients mi"
        " JOIN ingredient_allergens ia ON ia.ingredient_id = mi.ingredient_id"
        " WHERE mi.menu_item_id = ? ORDER BY ia.allergen_code",
        (item_id,),
    )
    return [row["allergen_code"] for row in rows]


def _served_on(conn, item_id, service_date):
    return conn.execute(
        "SELECT 1 FROM menu_item_serving_days WHERE menu_item_id = ? AND weekday = ?",
        (item_id, service_date.isoweekday()),
    ).fetchone() is not None


def _describe_item(conn, ctx, row):
    return {
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "price_eur": _format_eur(row["price_cents"]),
        "price_cents": row["price_cents"],
        "labels": _labels_of(conn, row["id"]),
        "allergens": _allergens_of(conn, row["id"]),
        "served_today": _served_on(conn, row["id"], ctx.service_date),
    }


def _parse_lines(items):
    """Validate order lines and merge repeated dishes."""
    if not isinstance(items, (list, tuple)) or not items:
        raise ToolError("invalid_argument", "items must be a non-empty list of order lines.")
    merged = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ToolError("invalid_argument", "Each order line needs a name and a quantity.")
        name = item["name"].strip()
        quantity = item.get("quantity")
        if not name or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ToolError(
                "invalid_argument", "Each order line needs a name and a quantity of at least 1."
            )
        line = merged.setdefault(name.casefold(), {"name": name, "quantity": 0})
        line["quantity"] += quantity
        if line["quantity"] > MAX_QUANTITY_PER_ITEM:
            raise ToolError(
                "invalid_argument", f"The quantity per dish cannot be over {MAX_QUANTITY_PER_ITEM}."
            )
    return list(merged.values())


def _find_lines(conn, lines):
    """Split order lines into dishes found in the database and names that are not there."""
    found = []
    missing = []
    for line in lines:
        row = conn.execute(
            "SELECT id, name, price_cents FROM menu_items WHERE name = ?", (line["name"],)
        ).fetchone()
        if row is None:
            missing.append(line["name"])
        else:
            found.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "quantity": line["quantity"],
                    "price_cents": row["price_cents"],
                }
            )
    return found, missing


def _require_all_found(conn, lines):
    found, missing = _find_lines(conn, lines)
    if missing:
        raise ToolError(
            "item_not_found", f"Menu item not found: {_quote_names(missing)}.", items=missing
        )
    return found


def _quote_names(names):
    return ", ".join(f"'{name}'" for name in names)


def _price_lines(found):
    lines = [
        {
            "name": line["name"],
            "quantity": line["quantity"],
            "unit_price_eur": _format_eur(line["price_cents"]),
            "unit_price_cents": line["price_cents"],
            "line_total_eur": _format_eur(line["price_cents"] * line["quantity"]),
            "line_total_cents": line["price_cents"] * line["quantity"],
        }
        for line in found
    ]
    return lines, sum(line["line_total_cents"] for line in lines)


def _read_stock(ctx, found):
    """Return the lines with portions left. A dish missing from the API has unknown stock."""
    portions = ctx.inventory.get_portions()
    stock = []
    for line in found:
        if line["id"] not in portions:
            raise InventoryUnavailable(f"the inventory service has no data for {line['name']}")
        stock.append({**line, "portions_left": portions[line["id"]]})
    return stock


@_tool
def search_menu(ctx, query=None, category=None, max_price_eur=None):
    """Find dishes by words in the name or description, category, and maximum price."""
    category = _resolve_category(category)
    max_price_cents = _to_cents(max_price_eur, "max_price_eur")
    if query is not None and not isinstance(query, str):
        raise ToolError("invalid_argument", "query must be text.")

    conditions = []
    params = []
    for word in (query or "").split():
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("(m.name LIKE ? ESCAPE '\\' OR m.description LIKE ? ESCAPE '\\')")
        params += [f"%{escaped}%", f"%{escaped}%"]
    if category is not None:
        conditions.append("m.category = ?")
        params.append(category)
    if max_price_cents is not None:
        conditions.append("m.price_cents <= ?")
        params.append(max_price_cents)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with closing(connect(ctx.db_path, read_only=True)) as conn:
        rows = conn.execute(
            f"SELECT {ITEM_COLUMNS} FROM menu_items m {where} ORDER BY m.id", params
        ).fetchall()
        return {"ok": True, "items": [_describe_item(conn, ctx, row) for row in rows]}


@_tool
def filter_dietary_options(
    ctx, required_labels=None, excluded_allergens=None, category=None, max_price_eur=None
):
    """Find dishes served today with all required labels and none of the excluded allergens."""
    category = _resolve_category(category)
    max_price_cents = _to_cents(max_price_eur, "max_price_eur")

    with closing(connect(ctx.db_path, read_only=True)) as conn:
        labels = _resolve_labels(conn, required_labels)
        allergens = _resolve_allergens(conn, excluded_allergens)
        label_marks = ", ".join("?" * len(labels))
        allergen_marks = ", ".join("?" * len(allergens))
        rows = conn.execute(
            f"""
            SELECT {ITEM_COLUMNS} FROM menu_items m
            JOIN menu_item_serving_days d ON d.menu_item_id = m.id AND d.weekday = ?
            WHERE (? IS NULL OR m.category = ?)
              AND (? IS NULL OR m.price_cents <= ?)
              AND (SELECT COUNT(*) FROM menu_item_labels l
                   WHERE l.menu_item_id = m.id AND l.label_code IN ({label_marks})) = ?
              AND NOT EXISTS (SELECT 1 FROM menu_item_ingredients mi
                              JOIN ingredient_allergens ia ON ia.ingredient_id = mi.ingredient_id
                              WHERE mi.menu_item_id = m.id
                                AND ia.allergen_code IN ({allergen_marks}))
            ORDER BY m.id
            """,
            (
                ctx.service_date.isoweekday(),
                category,
                category,
                max_price_cents,
                max_price_cents,
                *labels,
                len(labels),
                *allergens,
            ),
        ).fetchall()
        return {
            "ok": True,
            "items": [_describe_item(conn, ctx, row) for row in rows],
            "required_labels": labels,
            "excluded_allergens": allergens,
        }


@_tool
def get_ingredients(ctx, item_name):
    """Return a dish's ingredients and allergens from the ingredient table."""
    if not isinstance(item_name, str):
        raise ToolError("invalid_argument", "item_name must be text.")
    with closing(connect(ctx.db_path, read_only=True)) as conn:
        row = conn.execute(
            "SELECT id, name FROM menu_items WHERE name = ?", (item_name.strip(),)
        ).fetchone()
        if row is None:
            raise ToolError(
                "item_not_found", f"Menu item not found: '{item_name}'.", items=[item_name]
            )
        ingredients = conn.execute(
            "SELECT i.id, i.name FROM ingredients i"
            " JOIN menu_item_ingredients mi ON mi.ingredient_id = i.id"
            " WHERE mi.menu_item_id = ? ORDER BY i.name",
            (row["id"],),
        ).fetchall()
        return {
            "ok": True,
            "item": row["name"],
            "ingredients": [
                {
                    "name": ingredient["name"],
                    "allergens": [
                        allergen["allergen_code"]
                        for allergen in conn.execute(
                            "SELECT allergen_code FROM ingredient_allergens"
                            " WHERE ingredient_id = ? ORDER BY allergen_code",
                            (ingredient["id"],),
                        )
                    ],
                }
                for ingredient in ingredients
            ],
            "allergens": _allergens_of(conn, row["id"]),
        }


@_tool
def check_availability(ctx, items):
    """Report the portions left per dish from the inventory API, never an invented value."""
    lines = _parse_lines(items)
    with closing(connect(ctx.db_path, read_only=True)) as conn:
        found = _require_all_found(conn, lines)
    try:
        stock = _read_stock(ctx, found)
    except InventoryUnavailable as exc:
        return _error("inventory_unavailable", f"Availability could not be checked: {exc}.")
    result = [
        {
            "name": line["name"],
            "quantity": line["quantity"],
            "portions_left": line["portions_left"],
            "sold_out": line["portions_left"] == 0,
            "available": line["portions_left"] >= line["quantity"],
        }
        for line in stock
    ]
    return {"ok": True, "items": result, "all_available": all(row["available"] for row in result)}


@_tool
def calculate_total(ctx, items, budget_eur=None):
    """Add integer cents from database prices and compare the total with the budget."""
    lines = _parse_lines(items)
    budget_cents = _to_cents(budget_eur, "budget_eur")
    with closing(connect(ctx.db_path, read_only=True)) as conn:
        found = _require_all_found(conn, lines)
    priced, subtotal = _price_lines(found)
    result = {
        "ok": True,
        "lines": priced,
        "subtotal_eur": _format_eur(subtotal),
        "subtotal_cents": subtotal,
        "budget_eur": None,
        "within_budget": None,
        "over_budget_by_eur": None,
        "over_budget_by_cents": None,
    }
    if budget_cents is not None:
        over = max(subtotal - budget_cents, 0)
        result.update(
            budget_eur=_format_eur(budget_cents),
            within_budget=over == 0,
            over_budget_by_eur=_format_eur(over),
            over_budget_by_cents=over,
        )
    return result


def _problem(code, message, **extra):
    return {"code": code, "message": message, **extra}


def _pickup_problems(ctx, pickup_time):
    match = isinstance(pickup_time, str) and re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", pickup_time)
    if not match:
        return [_problem("invalid_pickup_time", "The pickup time must have the format HH:MM.")]
    if not ctx.pickup_open <= time(int(match[1]), int(match[2])) <= ctx.pickup_close:
        hours = f"{ctx.pickup_open:%H:%M}-{ctx.pickup_close:%H:%M}"
        return [
            _problem(
                "outside_pickup_hours",
                f"Pickup time {pickup_time} is outside the pickup hours {hours}.",
            )
        ]
    return []


def _item_problems(conn, ctx, line, labels, allergens):
    name = line["name"]
    problems = []
    if not _served_on(conn, line["id"], ctx.service_date):
        problems.append(
            _problem("not_served_today", f"{name} is not served on the service day.", item=name)
        )
    absent_labels = sorted(set(labels) - set(_labels_of(conn, line["id"])))
    if absent_labels:
        problems.append(
            _problem(
                "missing_label",
                f"{name} does not have the labels: {', '.join(absent_labels)}.",
                item=name,
                labels=absent_labels,
            )
        )
    present_allergens = sorted(set(allergens) & set(_allergens_of(conn, line["id"])))
    if present_allergens:
        problems.append(
            _problem(
                "contains_allergen",
                f"{name} contains: {', '.join(present_allergens)}.",
                item=name,
                allergens=present_allergens,
            )
        )
    return problems


def _stock_problems(ctx, found):
    if not found:
        return []
    try:
        stock = _read_stock(ctx, found)
    except InventoryUnavailable as exc:
        return [_problem("inventory_unavailable", f"Availability could not be checked: {exc}.")]
    problems = []
    for line in stock:
        name = line["name"]
        if line["portions_left"] == 0:
            problems.append(_problem("sold_out", f"{name} is sold out.", item=name))
        elif line["portions_left"] < line["quantity"]:
            problems.append(
                _problem(
                    "insufficient_stock",
                    f"Only {line['portions_left']} portions of {name} are left.",
                    item=name,
                    portions_left=line["portions_left"],
                )
            )
    return problems


def _find_same_draft(conn, draft, found):
    """Return the ID of an awaiting draft with identical content, so that a retry adds no row."""
    candidates = conn.execute(
        "SELECT id FROM draft_orders WHERE status = ? AND service_date = ? AND pickup_time = ?"
        " AND budget_cents IS ? AND required_labels = ? AND excluded_allergens = ?"
        " AND subtotal_cents = ?",
        (
            DRAFT_STATUS,
            draft["service_date"],
            draft["pickup_time"],
            draft["budget_cents"],
            draft["required_labels"],
            draft["excluded_allergens"],
            draft["subtotal_cents"],
        ),
    ).fetchall()
    expected = {(line["id"], line["quantity"]) for line in found}
    for candidate in candidates:
        rows = conn.execute(
            "SELECT menu_item_id, quantity FROM order_items WHERE draft_order_id = ?",
            (candidate["id"],),
        )
        if {(row["menu_item_id"], row["quantity"]) for row in rows} == expected:
            return candidate["id"]
    return None


def _save_draft(ctx, draft, found):
    """Save the draft and its lines in one transaction. Return (draft ID, already existed)."""
    with closing(connect(ctx.db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing_id = _find_same_draft(conn, draft, found)
        if existing_id is not None:
            return existing_id, True
        draft_id = conn.execute(
            "INSERT INTO draft_orders (status, service_date, pickup_time, budget_cents,"
            " required_labels, excluded_allergens, subtotal_cents, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                DRAFT_STATUS,
                draft["service_date"],
                draft["pickup_time"],
                draft["budget_cents"],
                draft["required_labels"],
                draft["excluded_allergens"],
                draft["subtotal_cents"],
                datetime.now(ctx.timezone).isoformat(timespec="seconds"),
            ),
        ).lastrowid
        conn.executemany(
            "INSERT INTO order_items (draft_order_id, menu_item_id, quantity, unit_price_cents)"
            " VALUES (?, ?, ?, ?)",
            [(draft_id, line["id"], line["quantity"], line["price_cents"]) for line in found],
        )
        return draft_id, False


@_tool
def draft_order(
    ctx, items, pickup_time, required_labels=None, excluded_allergens=None, budget_eur=None
):
    """Save a draft only when every check passes. This never orders or pays."""
    lines = _parse_lines(items)
    budget_cents = _to_cents(budget_eur, "budget_eur")

    with closing(connect(ctx.db_path, read_only=True)) as conn:
        labels = _resolve_labels(conn, required_labels)
        allergens = _resolve_allergens(conn, excluded_allergens)
        found, missing = _find_lines(conn, lines)
        problems = _pickup_problems(ctx, pickup_time)
        problems += [
            _problem("item_not_found", f"Menu item not found: '{name}'.", item=name)
            for name in missing
        ]
        for line in found:
            problems += _item_problems(conn, ctx, line, labels, allergens)

    priced, subtotal = _price_lines(found)
    if budget_cents is not None and not missing and subtotal > budget_cents:
        over = _format_eur(subtotal - budget_cents)
        problems.append(
            _problem(
                "over_budget",
                f"The total of {_format_eur(subtotal)} EUR is {over} EUR over the budget"
                f" of {_format_eur(budget_cents)} EUR.",
                subtotal_eur=_format_eur(subtotal),
                budget_eur=_format_eur(budget_cents),
                over_budget_by_eur=over,
            )
        )
    problems += _stock_problems(ctx, found)
    if problems:
        return _error("draft_refused", "The draft was not saved.", problems=problems)

    draft = {
        "service_date": ctx.service_date.isoformat(),
        "pickup_time": pickup_time,
        "budget_cents": budget_cents,
        "required_labels": json.dumps(labels),
        "excluded_allergens": json.dumps(allergens),
        "subtotal_cents": subtotal,
    }
    draft_id, already_existed = _save_draft(ctx, draft, found)
    return {
        "ok": True,
        "draft": {
            "draft_id": draft_id,
            "status": DRAFT_STATUS,
            "service_date": draft["service_date"],
            "pickup_time": pickup_time,
            "lines": priced,
            "subtotal_eur": _format_eur(subtotal),
            "subtotal_cents": subtotal,
            "budget_eur": None if budget_cents is None else _format_eur(budget_cents),
            "required_labels": labels,
            "excluded_allergens": allergens,
        },
        "already_existed": already_existed,
        "message": "Draft saved. The customer must confirm it. No order or payment was made.",
    }


TOOLS = (
    search_menu,
    filter_dietary_options,
    get_ingredients,
    check_availability,
    calculate_total,
    draft_order,
)
