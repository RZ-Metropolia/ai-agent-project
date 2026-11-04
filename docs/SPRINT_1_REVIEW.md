# Sprint 1 Review — Restaurant Order Agent

- **Sprint:** 1 (2026-10-28 to 2026-11-04)
- **Team:** Person A (Product Owner), Person B (Scrum Master), Person C
- **Sprint Goal:** "A customer can ask in natural language for a pickup order that matches a diet and a budget, and the agent creates a verified order draft using only database and inventory-API data."

## Was the Sprint Goal met?

**Mostly yes.** The agent answers natural-language requests with Qwen, calls the six tools, uses the SQLite database and the mock inventory API, and saves an order draft only when every rule passes. It never orders or pays. The evaluation shows this in both Groq and local Colab mode (see [SPRINT_1_EVALUATION.md](SPRINT_1_EVALUATION.md)).

It is not fully reliable yet: in 2 of 16 Groq runs, Groq refused a broken tool call and the agent stopped without an answer. No run created an unsafe draft.

## Increment shown

The demo request: *"Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros."*

The agent calls `filter_dietary_options` (vegetarian), `check_availability`, and `draft_order`. It saves one draft: Margherita Pizza + Lemonade, 16.00 €, status `awaiting_customer_confirmation`. The subtotal equals the database prices (12.50 € + 3.50 €).

Entry points: `notebooks/demo.ipynb` (Colab, Groq and local mode) and `python -m src.cli --trace` (command line).

## Completed work

| Item             | What was delivered                                                                                                        | Evidence                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| PBI-01 to PBI-03 | SQLite schema with synthetic seed data; `search_menu`, `filter_dietary_options`, `get_ingredients`                        | `data/`, `src/db.py`, `src/tools.py`; unit tests in `tests/test_db.py` and `tests/test_tools.py`; E-02 and E-03 pass |
| PBI-04           | Mock inventory REST API (normal, outage, bad JSON, slow) and a client with timeout and error checks; `check_availability` | `src/inventory_api.py`, `src/inventory_client.py`; E-04 (sold out) and E-06 (HTTP 503) pass in all runs              |
| PBI-05           | `calculate_total` with integer cents and a budget check                                                                   | 2 × Grilled Salmon = 39.80 €, 9.80 € over a 30 € budget (E-07)                                                       |
| PBI-06           | `draft_order` that checks all rules again and fails closed when the API is down                                           | No refused scenario saved a draft (E-04 to E-08)                                                                     |
| PBI-07           | LangChain tool wrappers and executor, Groq tool-calling loop with limits and a trace, CLI, Colab notebook                 | `src/agent_tools.py`, `src/agent.py`, `src/cli.py`, `notebooks/demo.ipynb`; Groq runs in `docs/eval_results/`        |
| PBI-08           | Local Qwen3.5-4B (4-bit) on a Colab GPU with the same tools                                                               | Local results in `docs/eval_results/`; 6 Pass, 2 Partial, 0 Fail                                                     |
| PBI-09           | Evaluation runner and 8 assistant-level scenarios in both modes                                                           | `src/evaluation.py`, `SPRINT_1_EVALUATION.md`                                                                        |

## Partially completed work

| Item             | What is missing                                                                                                                                                      | Next action                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Groq reliability | Groq refused a broken tool call (HTTP 400 `tool_use_failed`) in E-01 run 1 and E-07 run 2. The retry did not help, because it sent the same prompt at temperature 0. | Retry with a short note that names the correct tools, then run E-01 and E-07 again.  |
| E-05 answer      | The "no match" answer is correct, but it does not name the nearest dish (Berry Sorbet, 4.90 €). Partial in both modes.                                               | Decide whether this is required, then update the acceptance criterion or the prompt. |
| Tool contract    | `docs/CONTRACT.md` still has the status "draft, waiting for review".                                                                                                 | Person B approves it.                                                                |
| Documentation    | The Product Owner field (Person A) and the PBI statuses in `PRODUCT_BACKLOG.md`, and some statuses in `SPRINT_1_BACKLOG.md`, are not updated yet.                    | Update them before submission.                                                       |

## Not completed or moved

| Item                              | Decision                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| PBI-12: confirm or cancel a draft | Moved to Sprint 2. The schema already allows the statuses `confirmed` and `cancelled`, but no code writes them yet. |
| Streamlit GUI, MCP, RAG           | Sprint 2, as planned by the course.                                                                                 |

## Scope decisions during the sprint

- **Runs per scenario changed from 3 to 2** for Groq (commit `0d96226`).
- **A retry was added** for Groq tool-call errors (commit `fb4214a`), after the first runs showed refused tool calls.

## Feedback

No external feedback yet.

## Changes to the Product Backlog

- **New item:** retry a refused Groq tool call with a corrective note, and run E-01 and E-07 again.
- **New item:** decide the E-05 acceptance criterion (must the answer name the nearest dish?).
- **Confirmed for Sprint 2:** PBI-12 (confirm or cancel a draft).

## Scrum events

| Event                   | What happened                                                                                                                                                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sprint Planning         | Started on 2026-10-28, in a meeting on Zoom and WeChat, when the team chose Project 7 (Restaurant Ordering Assistant). The team then set the Sprint Goal, selected PBI-01 to PBI-09, split the work at `src/tools.py`, and agreed on the tool contract. |
| Daily Scrum / check-ins | Once a day, in meetings on Zoom and messages on WeChat. The team discussed the project content and progress. One obstacle that was raised: Groq refused some tool calls in the first evaluation runs, so a retry was added.                             |
| Sprint Review           | 2026-11-04, on Zoom and WeChat. The team checked the evaluation results and the E-01 demo, and agreed on the changes to the Product Backlog in this file.                                                                                               |
| Sprint Retrospective    | 2026-11-04, on Zoom and WeChat. See the 4Ls below.                                                                                                                                                                                                      |

## Retrospective (4Ls)

The team did the retrospective together. The table shows the team's shared view.

|                | Team                                                                                                                                                                                                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Liked**      | We agreed on the tool contract (`CONTRACT.md`) at the start.                                                                                                                                                                                                                      |
| **Learned**    | The same request can pass once and fail once on Groq, so one successful run does not prove reliability; we must run it several times. Rules belong in the code, not in the model: when the model made mistakes, the tool checks stopped them, and no wrong order draft was saved. |
| **Lacked**     | Our time management was not perfect. Some work was done in a short time, which caused stress.                                                                                                                                                                                     |
| **Longed for** | More time, tasks spread more evenly over the sprint, and planning ahead.                                                                                                                                                                                                          |

### Team summary

- **One thing that helped the team:** Agreeing on the tool contract early let us build the data layer and the agent layer at the same time.
- **One problem in the way of working:** The heavy work was concentrated in a short period, because we did not plan the time well enough.
- **One specific improvement for Sprint 2:** Plan the time better and earlier: split the work into tasks with dates at Sprint Planning, so that it is spread over the whole sprint.
