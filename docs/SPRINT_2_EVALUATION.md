# Sprint 2 Assistant Evaluation — Restaurant Order Agent

This file evaluates the complete assistant, from a request to the answer. Function unit tests are separate: see [SPRINT_2_UNIT_TESTS.md](SPRINT_2_UNIT_TESTS.md). The Sprint 1 evaluation stays in [SPRINT_1_EVALUATION.md](SPRINT_1_EVALUATION.md).

## Test setup

| Item | Value |
| --- | --- |
| Date of the runs | 2026-11-15 (Groq runner and Streamlit) |
| Groq model | `qwen/qwen3.8-27b`, temperature 0, at most 800 output tokens per reply |
| Local model (Colab) | `Qwen/Qwen3.5-4B`, 4-bit (NF4), Colab GPU — **not run yet for Sprint 2** |
| Code version | Working tree on top of commit `0e852d9`; `seed.json` version 1.0 |
| Database | A fresh database for each scenario run |
| API state | Normal stock from `mock_inventory.json`; outage switch on only for E-06 |
| MCP state | The MCP server starts normally; for E-11 its start command is broken on purpose |
| Fixed conditions | Service day fixed to Friday 2026-11-06; pickup hours 11:00–21:00 |
| Runs per scenario | 2 with the runner; 1 by hand in Streamlit |

## How we checked correctness

- **Runner:** `python -m src.evaluation --mode groq --runs 2`. It sends each request through the agent loop, the executor, the tools, the MCP client, and the MCP server. Only the Streamlit page is not part of the runner.
- **Tool choice and path:** the trace records each tool call, its arguments, its result, and its path (`direct` or `mcp`).
- **Grounded facts:** prices, allergens, and stock in the answer are compared with the tool results, which come from SQLite and the inventory API.
- **Database check:** after each run, the runner reads the drafts back from SQLite. For the MCP scenarios it checks the draft status, so an answer that says "cancelled" fails if the database does not agree.
- **Safe handling:** in refusal scenarios, no draft may be saved or changed.
- **A person reads each answer.** The answer checks only look for key words.
- **MCP scenarios start with one saved draft** (Margherita Pizza and Lemonade, 18:30, 16.00 €). The runner saves it with `draft_order` before the request, so the scenario does not depend on an earlier model answer.

**Result rule:** Pass = all checks pass. Partial = only a non-critical check fails. Fail = a critical check fails.

The details of every run (answers, checks, tool traces) are in [eval_results/groq_2026-11-15_0004.json](eval_results/groq_2026-11-15_0004.json).

## Evaluation record

| ID | Scenario / user request | Path exercised | Expected behavior | Observed behavior and source/tool evidence | Result |
|---|---|---|---|---|---|
| E-01 (Sprint 1 normal task) | "Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros." | Existing tools: database, inventory API | One draft; vegetarian, in stock, at most 20 €; subtotal equals the database prices. | Both runs: `filter_dietary_options`, `check_availability` (8 pizzas, 20 lemonades), `draft_order` with label vegetarian, budget 20, pickup 18:30. One draft in SQLite: Margherita Pizza + Lemonade, 1600 cents. The answer says 16.00 € and tells the customer to use the Confirm button. | Run 1: Pass; Run 2: Pass |
| E-02 (Sprint 1 database filter) | "Which main courses are both vegan and gluten-free today?" | Database tool | Only the dishes that SQL returns: Vegan Thai Curry. | Both runs: `filter_dietary_options` with `vegan`, `gluten_free`, and `category="main"`. Answer: only Vegan Thai Curry, 14.50 €. | Pass; Pass |
| E-03 (Sprint 1 allergy) | "I have a peanut allergy. Is the Vegan Thai Curry safe for me to order?" | Database tool | Not safe; allergens from the ingredient table (peanuts, soy). | Both runs: `get_ingredients` returned peanuts and soy. Answer: contains peanuts, not safe. It does not mention soy (non-critical check). | Partial; Partial |
| E-04 (Sprint 1 external API) | "Please draft a pickup order for one Mushroom Risotto at 19:00." (0 portions) | Inventory API | Sold out; no draft. | Both runs: `search_menu`, `check_availability`: 0 portions. Answer: sold out (0 portions left). No draft. | Pass; Pass |
| E-05 (Sprint 1 no match) | "I want a vegan dessert that costs less than 4 euros." | Database tool, empty result | "No match"; no invented dish. | Both runs: the filter returned an empty list. Answer: no vegan dessert under 4 €. It does not name Berry Sorbet, 4.90 € (non-critical check). | Partial; Partial |
| E-06 (Sprint 1 API failure) | "Please draft a pickup order for one Margherita Pizza at 18:30." while the API returns HTTP 503 | Inventory API failure | No draft; no stock value. | Both runs: `check_availability` returned `inventory_unavailable`. Answer: the stock cannot be verified, "I won't guess at stock levels". No draft. | Pass; Pass |
| E-07 (Sprint 1 budget) | "Order 2 Grilled Salmon for pickup at 18:00. My budget is 30 euros." | Existing tools | 39.80 €, 9.80 € over; no draft. | Both runs: `draft_order` refused with `over_budget`. The answer copies 39.80 and 9.80 from the tool. No draft. | Pass; Pass |
| E-08 (Sprint 1 invalid input) | "Draft one Falafel Wrap for pickup at 23:30." | Existing error handling | Outside the pickup hours; no draft. | Both runs: no tool call. The answer gives the hours 11:00–21:00 from the system prompt. No draft. | Pass; Pass |
| E-09 (MCP success) | "Please cancel my saved order draft." | Assistant → MCP client → MCP server → SQLite | The draft is cancelled through MCP, and the answer says so. | Both runs: `list_drafts` (MCP) returned draft 1, then `cancel_draft(draft_id=1)` (MCP) returned status `cancelled`. SQLite: draft 1 is `cancelled`. Answer: "Your draft (Margherita Pizza + Lemonade, €16.00) has been cancelled." | Pass; Pass |
| E-10 (MCP no match) | "Please cancel draft number 99." | Assistant → MCP client → MCP server (no matching draft) | Clear "not found"; the existing draft is unchanged. | Both runs: `cancel_draft(draft_id=99)` (MCP) returned `draft_not_found`, then `list_drafts` (MCP). SQLite: draft 1 still awaits confirmation. Answer: "There's no draft number 99", then it lists draft 1 from the tool result and asks whether to cancel it. | Pass; Pass |
| E-11 (MCP server failure) | "Which order drafts do I have?" while the MCP server cannot start | Assistant → MCP client (server unavailable) | Says the drafts cannot be read; invents no draft. | Both runs: `list_drafts` returned `mcp_unavailable`. Answer: the order service is not available, please try again. It names no dish and no total. SQLite: draft 1 unchanged. | Pass; Pass |
| G-01 (Streamlit) | In the page: the E-01 request; then Confirm with the outage switch on; then "Please cancel my draft." | Streamlit → assistant → existing tools; Confirm button → MCP client → MCP server → inventory API; assistant → MCP | The page shows the answer, the tool calls, and the draft. Confirm is refused during the outage. The cancel changes the cart. | One run by hand in a browser, live on Groq. Answer: Margherita Pizza €12.50 + Lemonade €3.50 = €16.00, "Tool calls (3)". Sidebar: Draft #1, pickup 18:30, "Waiting for your confirmation", Total 16.00 €. Confirm during the outage: "The draft was not confirmed. Availability could not be checked: the inventory service returned HTTP 503."; the draft kept its buttons. After the cancel request: `cancel_draft · MCP server · ok`, and the sidebar showed "Cancelled". The successful Confirm click was checked only by the automated page test, not by hand. | Pass |

## Sprint 1 and Sprint 2 on Groq

| ID | Sprint 1 (2026-11-04) | Sprint 2 (2026-11-15) | Difference |
| --- | --- | --- | --- |
| E-01 | Fail / Pass | Pass / Pass | Sprint 1 run 1 had a tool call that Groq refused. No refused call this time. |
| E-02 | Pass / Pass | Pass / Pass | Both Sprint 2 runs set `category="main"`. |
| E-03 | Pass / Pass | Partial / Partial | **Regression in the answer text:** it no longer mentions soy. The safety answer (peanuts, not safe) is still correct. The cause is not verified; the system prompt and the tool list changed. |
| E-04 | Pass / Pass | Pass / Pass | No difference. |
| E-05 | Partial / Partial | Partial / Partial | The same: Berry Sorbet is not named. |
| E-06 | Pass / Pass | Pass / Pass | No difference. |
| E-07 | Pass / Fail | Pass / Pass | Sprint 1 run 2 had a misspelled tool name. No refused call this time. |
| E-08 | Pass / Pass | Pass / Pass | No difference. |

## Variation between runs (Groq, Sprint 2)

- Every scenario had the same result in both runs.
- E-01 used different arguments: run 1 called the filter twice, with `category` and its own price limits (15 € for the main, 5 € for the drink); run 2 called it once with `max_price_eur=20`. Both chose Margherita Pizza and Lemonade. The price limits in run 1 were the model's own choice, not the customer's.
- E-03, E-04, E-05, E-07, E-08, E-09, E-10, and E-11 had word for word the same answers in both runs.

## Groq and local Qwen comparison

**The local model was not run in Sprint 2 yet.** It needs a Colab GPU. Run cell "Local mode" in `notebooks/demo.ipynb`, add the result file to `docs/eval_results/`, and fill in this table. The Sprint 1 local results are in [SPRINT_1_EVALUATION.md](SPRINT_1_EVALUATION.md).

| ID | Groq result | Local Qwen result | Difference and likely reason |
| --- | --- | --- | --- |
| E-01 to E-08 | 12 Pass, 4 Partial (16 runs) | `[not run]` | `[ ]` |
| E-09 | Pass / Pass | `[not run]` | `[ ]` |
| E-10 | Pass / Pass | `[not run]` | `[ ]` |
| E-11 | Pass / Pass | `[not run]` | `[ ]` |

## Short evaluation summary

- **Sprint 1 functions preserved:** all eight Sprint 1 scenarios still work on Groq: 12 of 16 runs pass and 4 are partial, with no fail. The safety rules held in every run: no draft was saved or changed when the request had to be refused. One answer got worse: E-03 no longer mentions soy.
- **New MCP-enabled task:** the customer can ask the assistant to show or cancel the drafts of their own session, and can confirm a draft with a button. Before a confirmation, the MCP server checks live stock again.
- **Streamlit interaction tested:** G-01, one run by hand: an order draft, a refused confirmation during an inventory outage, and a cancel through the assistant. Pass.
- **Results:** Groq runner: 22 scenario runs, 18 pass, 4 partial, 0 fail. Streamlit: 1 run, pass. Local Qwen: not run yet.
- **Important limitation and next improvement:**
  - *Groq limit.* The first complete run on 2026-11-14 failed in 21 of 22 scenario runs with HTTP 429: Groq's free tier now refuses a request that may write more than 1000 tokens. No draft was saved in those runs. We set a limit of 800 output tokens per reply and more retries, and ran the evaluation again. The second run took about 18 minutes because of the per-minute token limit. A live demo can be slow for the same reason. We did not keep the result file of the failed run.
  - *Corrective retry not seen in a real run.* The Sprint 1 failures (refused tool calls) did not happen in these 22 runs, so the new retry was never used. It is covered only by a unit test. We cannot say that it fixes the Sprint 1 failure.
  - *Next:* run the local model, and decide the E-03 and E-05 answer criteria (PBI-22).

## What we cannot conclude

- The menu and stock data are synthetic. The results do not prove real allergy safety.
- Eleven scenarios with two runs each do not prove general reliability for other requests.
- The Sprint 1 failures appeared in 2 of 16 runs. Their absence in 22 runs does not prove that they are gone.
- The Streamlit scenario ran once, in one browser, with one session. Several customers at the same time were not tested.
- The results are valid only for the model version and the Groq limits on the test date.
