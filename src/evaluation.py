"""Run the eight evaluation scenarios (E-01 to E-08) and check the results automatically.

Run from the project root:
    python -m src.evaluation --mode groq --runs 2
    python -m src.evaluation --mode local --runs 1

Each run uses a fresh database and a fixed service day (Friday). The checks read the tool
trace, the saved drafts in SQLite, and the answer text. Answer checks only look for key words,
so a person must still read each answer before the result goes into SPRINT_1_EVALUATION.md.
"""

import argparse
import json
import re
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.agent import build_model, run_agent
from src.agent_tools import make_tools
from src.config import ToolContext
from src.db import connect, init_db
from src.inventory_api import BackgroundServer
from src.inventory_client import InventoryClient, set_inventory_mode

SERVICE_DATE = date(2026, 11, 6)  # A Friday, as in the expected results.
RESULTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "eval_results"


@dataclass
class Scenario:
    id: str
    request: str
    check: object  # function(Outcome) -> list of (check name, critical, passed)
    api_mode: str = "normal"


@dataclass
class Outcome:
    answer: str
    tools: list  # Names of the tools that were called, in order.
    drafts: list  # Drafts saved in the database during the run.


def read_drafts(db_path):
    with closing(connect(db_path, read_only=True)) as conn:
        drafts = []
        for row in conn.execute("SELECT * FROM draft_orders ORDER BY id"):
            lines = conn.execute(
                "SELECT m.name, m.category, o.quantity,"
                " EXISTS (SELECT 1 FROM menu_item_labels l"
                "         WHERE l.menu_item_id = m.id AND l.label_code = 'vegetarian') AS vegetarian"
                " FROM order_items o JOIN menu_items m ON m.id = o.menu_item_id"
                " WHERE o.draft_order_id = ?",
                (row["id"],),
            ).fetchall()
            drafts.append(
                {
                    "pickup_time": row["pickup_time"],
                    "subtotal_cents": row["subtotal_cents"],
                    "budget_cents": row["budget_cents"],
                    "required_labels": json.loads(row["required_labels"]),
                    "lines": [dict(line) for line in lines],
                }
            )
        return drafts


# Helpers for the checks


def says(answer, *phrases):
    """True if the answer contains any of the phrases, ignoring case."""
    return any(phrase.lower() in answer.lower() for phrase in phrases)


def says_amount(answer, amount):
    """True if the answer contains the amount, for example 9.80 or 9,80, but not inside 39.80."""
    euros, cents = amount.split(".")
    return re.search(rf"(?<![\d.,]){euros}[.,]{cents}(?!\d)", answer) is not None


def called(outcome, *tool_names):
    return any(name in outcome.tools for name in tool_names)


def no_draft(outcome):
    return ("no draft is saved", True, not outcome.drafts)


def check_e01(o):
    draft = o.drafts[0] if len(o.drafts) == 1 else None
    lines = draft["lines"] if draft else []
    categories = sorted(line["category"] for line in lines for _ in range(line["quantity"]))
    return [
        ("exactly one draft is saved", True, draft is not None),
        ("draft has one main and one drink", True, categories == ["drink", "main"]),
        ("all items are vegetarian", True, bool(lines) and all(line["vegetarian"] for line in lines)),
        ("subtotal is at most 20.00", True, bool(draft) and draft["subtotal_cents"] <= 2000),
        ("pickup time is 18:30", True, bool(draft) and draft["pickup_time"] == "18:30"),
        (
            "draft_order got label vegetarian and budget 20",
            True,
            bool(draft) and "vegetarian" in draft["required_labels"] and draft["budget_cents"] == 2000,
        ),
        ("filter_dietary_options was called", False, called(o, "filter_dietary_options")),
        (
            "answer states the subtotal",
            False,
            bool(draft) and says_amount(o.answer, f"{draft['subtotal_cents'] / 100:.2f}"),
        ),
    ]


OTHER_MAINS = ("Margherita Pizza", "Mushroom Risotto", "Falafel Wrap", "Grilled Salmon",
               "Quinoa Bowl", "Beef Burger", "Chicken Caesar Salad", "Spinach Lasagne")


def check_e02(o):
    return [
        ("filter_dietary_options was called", True, called(o, "filter_dietary_options")),
        ("answer names Vegan Thai Curry", True, says(o.answer, "Vegan Thai Curry")),
        ("answer names no other main", False, not says(o.answer, *OTHER_MAINS)),
        no_draft(o),
    ]


def check_e03(o):
    return [
        ("ingredients were read from a tool", True,
         called(o, "get_ingredients", "filter_dietary_options")),
        ("answer mentions peanuts", True, says(o.answer, "peanut")),
        ("answer mentions soy", False, says(o.answer, "soy")),
        no_draft(o),
    ]


def check_e04(o):
    return [
        ("stock was checked", True, called(o, "check_availability", "draft_order")),
        ("answer says sold out", True,
         says(o.answer, "sold out", "out of stock", "no portions", "not available")),
        no_draft(o),
    ]


def check_e05(o):
    return [
        ("a menu tool was called", True, called(o, "filter_dietary_options", "search_menu")),
        ("answer names Berry Sorbet or 4.90", False,
         says(o.answer, "Berry Sorbet") or says_amount(o.answer, "4.90")),
        ("answer names no other dessert", False,
         not says(o.answer, "Vanilla Ice Cream", "Chocolate Brownie", "Tiramisu")),
        no_draft(o),
    ]


def check_e06(o):
    return [
        ("answer says stock could not be checked", True,
         says(o.answer, "could not be checked", "couldn't be checked", "cannot check",
              "can't check", "could not check", "unavailable", "not reachable", "not available")),
        ("stock was requested from a tool", False, called(o, "check_availability", "draft_order")),
        no_draft(o),
    ]


def check_e07(o):
    return [
        ("total was calculated by a tool", True, called(o, "calculate_total", "draft_order")),
        ("answer states 39.80", True, says_amount(o.answer, "39.80")),
        ("answer states 9.80 over budget", False, says_amount(o.answer, "9.80")),
        no_draft(o),
    ]


def check_e08(o):
    return [
        ("answer gives the pickup hours", True, says(o.answer, "21:00", "pickup hours", "9 pm")),
        no_draft(o),
    ]


SCENARIOS = (
    Scenario("E-01", "Prepare a vegetarian pickup order for one person at 18:30: one main course"
             " and one drink, with a total of at most 20 euros.", check_e01),
    Scenario("E-02", "Which main courses are both vegan and gluten-free today?", check_e02),
    Scenario("E-03", "I have a peanut allergy. Is the Vegan Thai Curry safe for me to order?",
             check_e03),
    Scenario("E-04", "Please draft a pickup order for one Mushroom Risotto at 19:00.", check_e04),
    Scenario("E-05", "I want a vegan dessert that costs less than 4 euros.", check_e05),
    Scenario("E-06", "Please draft a pickup order for one Margherita Pizza at 18:30.", check_e06,
             api_mode="outage"),
    Scenario("E-07", "Order 2 Grilled Salmon for pickup at 18:00. My budget is 30 euros.",
             check_e07),
    Scenario("E-08", "Draft one Falafel Wrap for pickup at 23:30.", check_e08),
)


def grade(checks):
    """Pass: all checks pass. Partial: only non-critical checks fail. Fail: a critical check fails."""
    if any(critical and not passed for _, critical, passed in checks):
        return "Fail"
    if any(not passed for _, _, passed in checks):
        return "Partial"
    return "Pass"


def run_scenario(model, scenario, inventory_url):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = init_db(Path(tmp) / "eval.db")
        ctx = ToolContext(
            db_path=db_path,
            inventory=InventoryClient(inventory_url),
            service_date=SERVICE_DATE,
            timezone=ZoneInfo("Europe/Berlin"),
        )
        set_inventory_mode(inventory_url, scenario.api_mode)
        try:
            result = run_agent(model, ctx, make_tools(ctx), scenario.request)
        finally:
            set_inventory_mode(inventory_url, "normal")
        outcome = Outcome(result.answer, [step["tool"] for step in result.trace], read_drafts(db_path))

    checks = scenario.check(outcome)
    return {
        "id": scenario.id,
        "request": scenario.request,
        "result": grade(checks),
        "answer": outcome.answer,
        "stop_reason": result.stop_reason,
        "tools": outcome.tools,
        "drafts": outcome.drafts,
        "checks": [{"check": n, "critical": c, "passed": p} for n, c, p in checks],
        "trace": result.trace,
    }


def run_evaluation(model, mode, runs=1, scenarios=SCENARIOS, save=True):
    """Run every scenario `runs` times. Print a summary and save the details as JSON."""
    results = []
    with BackgroundServer() as server:
        for run in range(1, runs + 1):
            for scenario in scenarios:
                row = {"run": run, **run_scenario(model, scenario, server.url)}
                results.append(row)
                failed = [c["check"] for c in row["checks"] if not c["passed"]]
                print(f"run {run} {row['id']}: {row['result']:<7} tools={row['tools']}"
                      + (f" failed={failed}" if failed else ""))

    if save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"{mode}_{datetime.now():%Y-%m-%d_%H%M}.json"
        path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved the details (answers, checks, tool traces) to {path}")
    print_summary(results)
    return results


def print_summary(results):
    runs = sorted({row["run"] for row in results})
    print("\n| ID | " + " | ".join(f"Run {run}" for run in runs) + " |")
    print("| --- |" + " --- |" * len(runs))
    for scenario_id in dict.fromkeys(row["id"] for row in results):
        cells = [row["result"] for row in results if row["id"] == scenario_id]
        print(f"| {scenario_id} | " + " | ".join(cells) + " |")
    passed = sum(row["result"] == "Pass" for row in results)
    print(f"\nPassed {passed} of {len(results)} scenario runs.")


def main():
    parser = argparse.ArgumentParser(description="Run the Sprint 1 evaluation scenarios.")
    parser.add_argument("--mode", choices=["groq", "local"], default="groq")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    run_evaluation(build_model(args.mode), args.mode, args.runs)


if __name__ == "__main__":
    main()
