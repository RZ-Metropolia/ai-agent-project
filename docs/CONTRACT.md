# Tool Contract — Restaurant Order Agent

This contract is the boundary between the data layer (`src/tools.py`) and the agent layer. Changes must be agreed by both sides.

Status: **draft, waiting for review by the agent-layer owner.**

## Calling the tools

Each tool is a plain Python function in `src/tools.py`. `tools.TOOLS` lists all six.

```python
from src.config import load_context
from src import tools

ctx = load_context()
tools.filter_dietary_options(ctx, required_labels=["vegan"], category="main")
```

The first parameter, `ctx` (`ToolContext`), holds the database path, inventory client, service date, and pickup hours. **The agent layer binds `ctx` itself and never shows it to the model**, so the model cannot change the service day or the database.

## Return format

Tools never raise an exception to the caller. Every result is a JSON-serializable dictionary.

```json
{"ok": true, "items": []}
```

```json
{"ok": false, "error": {"code": "item_not_found", "message": "Menu item not found: 'Pizza X'."}}
```

## Shared conventions

| Topic | Rule |
|---|---|
| Dish identity | Tools take the exact dish **name**, ignoring case. There is no fuzzy matching. A wrong ID could silently return another dish, while a wrong name returns an error. |
| `OrderLine` | `{"name": str, "quantity": int}`, with quantity 1–20. Repeated dishes are merged, and the merged quantity must also be at most 20. |
| Money input | Arguments ending in `_eur` take a number or numeric string, at most 2 decimals, not negative. |
| Money output | Both forms: `"subtotal_eur": "39.80"` and `"subtotal_cents": 3980`. Answers should use the `_eur` text and never recalculate. |
| Labels | `vegetarian`, `vegan`, `gluten_free`, `dairy_free`. Case, spaces, and hyphens are normalized (`Gluten-Free` works). |
| Allergens | The 14 EU codes: `gluten`, `crustaceans`, `eggs`, `fish`, `peanuts`, `soy`, `milk`, `tree_nuts`, `celery`, `mustard`, `sesame`, `sulphites`, `lupin`, `molluscs`. |
| Allergen aliases | The tools expand common words: `nuts` → `peanuts` + `tree_nuts`; `shellfish` → `crustaceans` + `molluscs`; `dairy`, `lactose` → `milk`; `wheat` → `gluten`. Singular and spelling variants also work (`egg`, `peanut`, `soya`, `sulfites`). |
| Unknown values | Unknown labels, allergens, and categories are refused and the allowed values are returned. They are never ignored: an ignored allergen would make an unsafe dish look safe. |
| Categories | `starter`, `main`, `dessert`, `drink`. |
| Service day | "Today" always means `ctx.service_date`. |
| Pickup time | `"HH:MM"` in 24-hour format. Both 11:00 and 21:00 are inside the pickup hours. |

### `MenuItem`

```json
{
  "name": "Berry Sorbet",
  "category": "dessert",
  "description": "Mixed berry sorbet with lemon.",
  "price_eur": "4.90",
  "price_cents": 490,
  "labels": ["dairy_free", "gluten_free", "vegan", "vegetarian"],
  "allergens": [],
  "served_today": true
}
```

## Tools

### `search_menu(ctx, query=None, category=None, max_price_eur=None)`

Returns dishes that match all given filters. Every word in `query` must appear in the name or description. Dishes not served today are included with `served_today: false`. No match returns an empty list.

```json
{"ok": true, "items": ["MenuItem"]}
```

### `filter_dietary_options(ctx, required_labels=None, excluded_allergens=None, category=None, max_price_eur=None)`

Returns dishes served today that have **all** required labels and **none** of the excluded allergens.

```json
{"ok": true, "items": ["MenuItem"], "required_labels": ["vegan"], "excluded_allergens": ["peanuts", "tree_nuts"]}
```

The returned lists show the codes after alias expansion.

### `get_ingredients(ctx, item_name)`

```json
{
  "ok": true,
  "item": "Vegan Thai Curry",
  "ingredients": [{"name": "Tofu", "allergens": ["soy"]}, {"name": "Peanuts", "allergens": ["peanuts"]}],
  "allergens": ["peanuts", "soy"]
}
```

An unknown dish returns `item_not_found`.

### `check_availability(ctx, items)`

`items` is a list of `OrderLine`.

```json
{
  "ok": true,
  "items": [{"name": "Mushroom Risotto", "quantity": 1, "portions_left": 0, "sold_out": true, "available": false}],
  "all_available": false
}
```

If the inventory API fails (HTTP error, timeout, bad JSON, or a dish missing from its response), the tool returns `inventory_unavailable` and no stock values.

### `calculate_total(ctx, items, budget_eur=None)`

Going over budget is a successful calculation, so `ok` stays `true`.

```json
{
  "ok": true,
  "lines": [{"name": "Grilled Salmon", "quantity": 2, "unit_price_eur": "19.90", "unit_price_cents": 1990, "line_total_eur": "39.80", "line_total_cents": 3980}],
  "subtotal_eur": "39.80",
  "subtotal_cents": 3980,
  "budget_eur": "30.00",
  "within_budget": false,
  "over_budget_by_eur": "9.80",
  "over_budget_by_cents": 980
}
```

Without a budget, the four budget fields are `null`. Within budget, the two `over_budget_by_*` fields are `"0.00"` and `0`.

### `draft_order(ctx, items, pickup_time, required_labels=None, excluded_allergens=None, budget_eur=None)`

Checks everything again, whatever the agent checked before, and saves a draft only when all checks pass.

```json
{
  "ok": true,
  "draft": {
    "draft_id": 1,
    "status": "awaiting_customer_confirmation",
    "service_date": "2026-11-06",
    "pickup_time": "18:30",
    "lines": ["same shape as calculate_total"],
    "subtotal_eur": "16.00",
    "subtotal_cents": 1600,
    "budget_eur": "20.00",
    "required_labels": ["vegetarian"],
    "excluded_allergens": []
  },
  "already_existed": false,
  "message": "Draft saved. The customer must confirm it. No order or payment was made."
}
```

A repeated call with identical content does not create a second draft. It returns the existing one with `already_existed: true`.

**Limitation:** there are no customers or sessions yet, so two customers with an identical request would share a draft. This must change when sessions arrive in Sprint 2.

A refused request saves nothing and lists every problem found:

```json
{
  "ok": false,
  "error": {"code": "draft_refused", "message": "The draft was not saved."},
  "problems": [
    {"code": "outside_pickup_hours", "message": "Pickup time 23:30 is outside the pickup hours 11:00-21:00."}
  ]
}
```

| Problem code | Meaning | Extra fields |
|---|---|---|
| `invalid_pickup_time` | The time is not `HH:MM`. | |
| `outside_pickup_hours` | The time is outside the pickup hours. | |
| `item_not_found` | The dish does not exist. The budget is not checked in this case. | `item` |
| `not_served_today` | The dish is not served on the service day. | `item` |
| `missing_label` | The dish lacks required labels. | `item`, `labels` |
| `contains_allergen` | The dish contains excluded allergens. | `item`, `allergens` |
| `over_budget` | The total is over the budget. | `subtotal_eur`, `budget_eur`, `over_budget_by_eur` |
| `sold_out` | No portions are left. | `item` |
| `insufficient_stock` | Fewer portions are left than requested. | `item`, `portions_left` |
| `inventory_unavailable` | Stock could not be checked (fail closed). | |

## Error codes

| Code | Returned by | Meaning |
|---|---|---|
| `invalid_argument` | all | Wrong type or value, for example an empty item list or a bad amount. |
| `unknown_label` | filter, draft | Unknown dietary label. Has `allowed`. |
| `unknown_allergen` | filter, draft | Unknown allergen. Has `allowed`. The agent must say that it cannot verify this allergen. |
| `unknown_category` | search, filter | Unknown category. Has `allowed`. |
| `item_not_found` | ingredients, availability, total | Unknown dish. Has `items` with the unknown names. |
| `inventory_unavailable` | availability | The inventory API failed. |
| `draft_refused` | draft | Business checks failed. Has `problems`. |
| `database_error` | all | SQLite failed. Nothing is saved. |

## Mock inventory API

| Request | Result |
|---|---|
| `GET /inventory` | `{"items": [{"item_id": 1, "name": "Margherita Pizza", "portions": 8}]}` |
| `POST /_admin/mode` with `{"mode": "normal"}` | Switches mode: `normal`, `outage` (HTTP 503), `bad_json`, `slow` (longer than the client timeout). For tests and the evaluation runner only. |

`src/inventory_client.py` has `set_inventory_mode(base_url, mode)` for switching the mode from code.

Start it with `python -m src.inventory_api`. In Colab, use `BackgroundServer` from `src/inventory_api.py`. Stock does not decrease when a draft is saved: that is PBI-20.
