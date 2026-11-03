-- Restaurant database schema.
-- Live stock is not stored here: it belongs to the inventory API.
-- Foreign keys are enforced per connection, see connect() in src/db.py.

-- Menu

CREATE TABLE menu_items (
  id          INTEGER PRIMARY KEY,  -- Set by the seed; shared with mock_inventory.json.
  name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
  category    TEXT NOT NULL CHECK (category IN ('starter', 'main', 'dessert', 'drink')),
  description TEXT NOT NULL DEFAULT '',
  price_cents INTEGER NOT NULL CHECK (price_cents > 0)
) STRICT;

CREATE TABLE menu_item_serving_days (
  menu_item_id INTEGER NOT NULL REFERENCES menu_items (id),
  weekday      INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),  -- ISO weekday: Friday = 5.
  PRIMARY KEY (menu_item_id, weekday)
) STRICT;

-- Dietary labels: what a dish declares about itself.

CREATE TABLE dietary_labels (
  code TEXT PRIMARY KEY
) STRICT;

CREATE TABLE menu_item_labels (
  menu_item_id INTEGER NOT NULL REFERENCES menu_items (id),
  label_code   TEXT NOT NULL REFERENCES dietary_labels (code),
  PRIMARY KEY (menu_item_id, label_code)
) STRICT;

-- Ingredients and allergens: a dish's allergens are derived from its ingredients.

CREATE TABLE ingredients (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE
) STRICT;

CREATE TABLE allergens (
  code TEXT PRIMARY KEY
) STRICT;

CREATE TABLE menu_item_ingredients (
  menu_item_id  INTEGER NOT NULL REFERENCES menu_items (id),
  ingredient_id INTEGER NOT NULL REFERENCES ingredients (id),
  PRIMARY KEY (menu_item_id, ingredient_id)
) STRICT;

CREATE TABLE ingredient_allergens (
  ingredient_id INTEGER NOT NULL REFERENCES ingredients (id),
  allergen_code TEXT NOT NULL REFERENCES allergens (code),
  PRIMARY KEY (ingredient_id, allergen_code)
) STRICT;

-- Order drafts: refused requests are never stored here.

CREATE TABLE draft_orders (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  -- 'confirmed' and 'cancelled' are reserved for PBI-12; Sprint 1 tools never write them.
  status             TEXT NOT NULL DEFAULT 'awaiting_customer_confirmation'
                     CHECK (status IN ('awaiting_customer_confirmation', 'confirmed', 'cancelled')),
  service_date       TEXT NOT NULL,  -- 'YYYY-MM-DD'
  pickup_time        TEXT NOT NULL,  -- 'HH:MM'
  budget_cents       INTEGER CHECK (budget_cents IS NULL OR budget_cents >= 0),
  required_labels    TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(required_labels)),
  excluded_allergens TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(excluded_allergens)),
  subtotal_cents     INTEGER NOT NULL CHECK (subtotal_cents >= 0),
  created_at         TEXT NOT NULL
) STRICT;

CREATE TABLE order_items (
  id               INTEGER PRIMARY KEY,
  draft_order_id   INTEGER NOT NULL REFERENCES draft_orders (id) ON DELETE CASCADE,
  menu_item_id     INTEGER NOT NULL REFERENCES menu_items (id),
  quantity         INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),  -- Price when the draft was made.
  UNIQUE (draft_order_id, menu_item_id)
) STRICT;
