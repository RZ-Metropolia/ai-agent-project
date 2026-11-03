"""LangChain wrappers for the six tools, and the executor that runs the model's tool calls.

The model sees only the argument schemas below. The context (`ctx`) is bound here, so the
model cannot change the database, the inventory API, or the service day.
"""

from functools import partial

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src import tools


class _Args(BaseModel):
    # An unknown argument is refused, never ignored.
    model_config = ConfigDict(extra="forbid")


class OrderLine(_Args):
    name: str = Field(description="Exact dish name, as returned by a menu tool.")
    quantity: int = Field(ge=1, le=20, description="Number of portions.")


LABELS = "Dietary labels: vegetarian, vegan, gluten_free, dairy_free."
ALLERGENS = "Allergens to avoid, for example peanuts, tree_nuts, gluten, milk, eggs, soy."
CATEGORY = "One of: starter, main, dessert, drink."


class SearchMenuArgs(_Args):
    query: str | None = Field(None, description="Words that must appear in the name or description.")
    category: str | None = Field(None, description=CATEGORY)
    max_price_eur: float | None = Field(None, ge=0, description="Highest price per dish in euros.")


class FilterDietaryOptionsArgs(_Args):
    required_labels: list[str] | None = Field(None, description=LABELS)
    excluded_allergens: list[str] | None = Field(None, description=ALLERGENS)
    category: str | None = Field(None, description=CATEGORY)
    max_price_eur: float | None = Field(None, ge=0, description="Highest price per dish in euros.")


class GetIngredientsArgs(_Args):
    item_name: str = Field(description="Exact dish name.")


class CheckAvailabilityArgs(_Args):
    items: list[OrderLine] = Field(min_length=1, description="Dishes and quantities to check.")


class CalculateTotalArgs(_Args):
    items: list[OrderLine] = Field(min_length=1, description="Dishes and quantities.")
    budget_eur: float | None = Field(None, ge=0, description="The customer's budget in euros.")


class DraftOrderArgs(_Args):
    items: list[OrderLine] = Field(min_length=1, description="Dishes and quantities.")
    pickup_time: str = Field(description="Pickup time as HH:MM, 24-hour format.")
    required_labels: list[str] | None = Field(None, description=LABELS)
    excluded_allergens: list[str] | None = Field(None, description=ALLERGENS)
    budget_eur: float | None = Field(None, ge=0, description="The customer's budget in euros.")


# (function, argument schema, description for the model)
TOOL_SPECS = (
    (
        tools.search_menu,
        SearchMenuArgs,
        "Search the menu by words, category, and maximum price. Includes dishes not served"
        " today, marked with served_today: false.",
    ),
    (
        tools.filter_dietary_options,
        FilterDietaryOptionsArgs,
        "Find dishes served today that have ALL required labels and NONE of the excluded"
        " allergens. Use this for diet and allergy requests.",
    ),
    (
        tools.get_ingredients,
        GetIngredientsArgs,
        "Get the ingredients and allergens of one dish. Use this for allergy questions.",
    ),
    (
        tools.check_availability,
        CheckAvailabilityArgs,
        "Check live stock (portions left) for dishes from the inventory system.",
    ),
    (
        tools.calculate_total,
        CalculateTotalArgs,
        "Calculate the exact total and compare it with a budget. Never add prices yourself.",
    ),
    (
        tools.draft_order,
        DraftOrderArgs,
        "Save an order draft for pickup today. It checks pickup hours, labels, allergens, budget,"
        " and stock again, and saves nothing if a check fails. It never orders or pays.",
    ),
)


def make_tools(ctx):
    """Return {tool name: LangChain tool} with `ctx` bound to each function.

    To build a model, only the schemas matter, so `ctx` can be None there.
    """
    return {
        func.__name__: StructuredTool.from_function(
            func=partial(func, ctx),
            name=func.__name__,
            description=description,
            args_schema=schema,
        )
        for func, schema, description in TOOL_SPECS
    }


def _refusal(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def execute_tool(tool_map, name, args):
    """Run one tool call from the model. Unknown tools and invalid arguments are refused."""
    tool = tool_map.get(name)
    if tool is None:
        return _refusal(
            "unknown_tool", f"Unknown tool: {name}. Allowed tools: {', '.join(tool_map)}."
        )
    try:
        parsed = tool.args_schema.model_validate(args)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, error['loc'])) or 'arguments'}: {error['msg']}"
            for error in exc.errors()
        )
        return _refusal("invalid_argument", f"Invalid arguments for {name}: {details}")
    return tool.func(**parsed.model_dump())
