# Sprint 1 Assistant Evaluation — Restaurant Order Agent

## Test setup

| Item                        | Value                                                                   |
| --------------------------- | ----------------------------------------------------------------------- |
| Date of the runs            | `[Date]`                                                                |
| Groq model                  | `qwen/qwen3.8-27b`                                                      |
| Local model (Colab)         | `Qwen/Qwen3.5-4B`, 4-bit (NF4), Colab GPU                               |
| Database version            | `[Seed file version or commit]`, fresh database for each evaluation run |
| API state                   | Normal stock from `mock_inventory.json`; outage switch on only for E-06 |
| Fixed conditions            | Service day fixed to Friday; temperature 0; pickup hours 11:00–21:00    |
| Number of runs per scenario | 3                                                                       |

## How we checked correctness

- **Tool choice:** The tool trace shows which tools the agent called. We compare it with the expected tools for each scenario.
- **Arguments:** The executor validates every argument with the Pydantic schema. We check the trace for the correct labels, allergens, items, and budget.
- **Grounded facts:** We compare prices, ingredients, allergens, and stock in the answer with a direct SQL query and with the API response.
- **Draft check:** We read the stored draft back from SQLite. Its subtotal must equal the sum of the database prices, and every item must pass the requested rules.
- **Safe handling:** In failure scenarios, no new draft row may exist, and the answer must state the reason.
- **Runner:** `python -m src.evaluation --mode groq --runs 3` (or the Colab notebook) runs the scenarios and does these checks automatically. The checks for each scenario are in `src/evaluation.py`, and each check is marked critical or non-critical. The answer checks only look for key words, so a person reads each answer before recording the result. The answers, checks, and tool traces are saved in `docs/eval_results/`.
- **Local runs:** local mode uses greedy decoding (no sampling), so it gives the same output each time. One run per scenario is enough there.

**Result rule:**

- **Pass:** All checks pass: correct tools, correct facts, and a correct draft or a correct refusal.
- **Partial:** Only a non-critical check fails. Example: the result is safe, but the answer does not state the total, or it mentions a non-matching item as an option.
- **Fail:** A critical check fails. Examples: invented data, an unsafe or missing draft, a draft created when it must be refused, or a missing key fact.

## Evaluation record

| ID                      | User request / condition                                                                                                      | Expected behavior                                                                                                                                                                                                                                                                                                                                     | Actual behavior and tool/data evidence | Result |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ------ |
| E-01 (normal task)      | "Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros." | Calls `filter_dietary_options` (vegetarian), checks stock, and calls `draft_order` with `required_labels=["vegetarian"]` and `budget_eur=20`. One draft is saved. All items are vegetarian and in stock. The subtotal is ≤ 20.00 € and equals the database prices (for example Margherita Pizza + Lemonade = 16.00 €). A sold-out dish is not chosen. | `[Not yet run]`                        | —      |
| E-02 (database filter)  | "Which main courses are both vegan and gluten-free today?"                                                                    | Calls `filter_dietary_options` with both labels and category `main`. The answer lists only the items that the direct SQL query returns (only Vegan Thai Curry).                                                                                                                                                                                       | `[Not yet run]`                        | —      |
| E-03 (database, safety) | "I have a peanut allergy. Is the Vegan Thai Curry safe for me to order?"                                                      | Calls `get_ingredients`. Says that the dish contains peanuts and is not safe. The allergens match the ingredient table (peanuts, soy). No guess from the dish name.                                                                                                                                                                                   | `[Not yet run]`                        | —      |
| E-04 (external API)     | "Please draft a pickup order for one Mushroom Risotto at 19:00." API shows 0 portions.                                        | Calls `check_availability` or `draft_order`. No draft is saved. The answer says the dish is sold out and can offer alternatives from tool data.                                                                                                                                                                                                       | `[Not yet run]`                        | —      |
| E-05 (no match)         | "I want a vegan dessert that costs less than 4 euros."                                                                        | Uses a filter tool. The answer says that no dish matches (the only vegan dessert, Berry Sorbet, costs 4.90 €). No invented dish.                                                                                                                                                                                                                      | `[Not yet run]`                        | —      |
| E-06 (API failure)      | Any order request while the inventory API returns HTTP 503.                                                                   | No draft is saved. The answer says that availability could not be checked. No invented stock value.                                                                                                                                                                                                                                                   | `[Not yet run]`                        | —      |
| E-07 (budget overrun)   | "Order 2 Grilled Salmon for pickup at 18:00. My budget is 30 euros."                                                          | Calls `calculate_total`. Total 39.80 €, 9.80 € over the budget. No draft is saved. The model does not calculate the total itself.                                                                                                                                                                                                                     | `[Not yet run]`                        | —      |
| E-08 (invalid input)    | "Draft one Falafel Wrap for pickup at 23:30."                                                                                 | No draft is saved. The answer says the time is outside the pickup hours 11:00–21:00.                                                                                                                                                                                                                                                                  | `[Not yet run]`                        | —      |

## Groq and local Qwen comparison

| ID | Groq result | Local Qwen result | Difference and likely reason |
| --- | --- | --- | --- |
| E-01 | `[ ]` | `[ ]` | `[ ]` |
| E-02 | `[ ]` | `[ ]` | `[ ]` |
| E-03 | `[ ]` | `[ ]` | `[ ]` |
| E-04 | `[ ]` | `[ ]` | `[ ]` |
| E-05 | `[ ]` | `[ ]` | `[ ]` |
| E-06 | `[ ]` | `[ ]` | `[ ]` |
| E-07 | `[ ]` | `[ ]` | `[ ]` |
| E-08 | `[ ]` | `[ ]` | `[ ]` |

## Variation between runs (Groq)

| ID | Run 1 | Run 2 | Run 3 | Observation |
| --- | --- | --- | --- | --- |
| E-01 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-02 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-03 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-04 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-05 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-06 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-07 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| E-08 | `[ ]` | `[ ]` | `[ ]` | `[ ]` |

## Short evaluation summary

> Complete after the runs, in your own words.

- **Scenarios completed:** `[number]`; **passed:** `[number]`; **partial/failed:** `[number]`.
- **What worked reliably:** `[observations with evidence]`.
- **Most important failure or limitation:** `[what happened, and likely reason]`.
- **What we would change or test next:** `[specific next action]`.

## What we cannot conclude

- The menu and stock data are synthetic. The results do not prove real allergy safety.
- Eight scenarios with three runs each do not prove general reliability for other requests.
- The results are valid only for the model versions listed in the test setup.
