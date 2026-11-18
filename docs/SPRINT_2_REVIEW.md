# Sprint 2 Review — Restaurant Order Agent

- **Sprint:** 2 (2026-11-05 to 2026-11-18)
- **Team:** Zongru Li (Product Owner), Juyin Tang (Scrum Master), Rui Zhao. All three are developers.
- **Sprint Goal:** "A customer can order in a Streamlit page: the assistant prepares a draft with the Sprint 1 tools, and the customer sees, cancels, or confirms their own drafts through an MCP server."

## Was the Sprint Goal met?

**Mostly yes.** In the Streamlit page, a request reaches Qwen, Qwen calls the Sprint 1 tools, and a draft appears in the cart. The assistant lists and cancels drafts through the MCP client and server, and the Confirm button confirms a draft through the same MCP server after a new stock check. Nothing is ordered or paid. Local Qwen in Colab reaches the same safe results, with more tool calls.

Not finished:

- The corrective retry (PBI-21) was never used in a real run, so we do not know whether it fixes the Sprint 1 failure.
- Groq's token limit makes requests slow.

## What Sprint 1 did, and what changed

| | Sprint 1 | Sprint 2 |
|---|---|---|
| Interface | Command-line chat and Colab notebook | Also a Streamlit page with a chat, a cart, and buttons |
| Tools for the model | 6 direct Python tools | The same 6, plus `list_drafts` and `cancel_draft` through MCP |
| Drafts | Saved; could not be confirmed or cancelled; no owner | Belong to a session; can be listed, cancelled, and confirmed |
| MCP | None | One server with 3 tools; one client used by the assistant and the page |
| Refused Groq tool call | Retry with the same prompt; raw error shown to the customer | Retry with a note that names the tools; friendly message |
| Unit tests | 154, results not saved | 239, results saved |
| Evaluation | 8 scenarios | The same 8, plus 3 MCP scenarios and 1 Streamlit scenario |

## Increment shown

1. **Existing workflow in Streamlit:** *"Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros."* The answer gives Margherita Pizza 12.50 € + Lemonade 3.50 € = 16.00 €. "Tool calls" shows the direct tools. The sidebar shows Draft #1.
2. **API failure:** switch on "Simulate an inventory API outage", then click **Confirm**. The page shows that availability could not be checked, and the draft still waits.
3. **MCP workflow:** *"Please cancel my draft."* "Tool calls" shows `cancel_draft · MCP server · ok`, and the sidebar shows "Cancelled".

Entry points: `streamlit run app.py`; also `python -m src.cli --trace` and `notebooks/demo.ipynb`.

## Completed work

| Item | What was delivered | Evidence |
|---|---|---|
| Sprint 1 baseline | The six tools, the database, and the inventory API work as before | E-01 to E-08 on Groq: 12 Pass, 4 Partial, 0 Fail |
| PBI-12 | Sessions for drafts; list, cancel, and confirm rules; a new stock check before a confirmation | `src/orders.py`; `tests/test_orders.py` |
| PBI-11 | MCP server with `list_drafts`, `cancel_draft`, `confirm_draft`; MCP client over stdio; two MCP tools for the assistant | `src/mcp_server/`, `src/mcp_client/`; E-09, E-10, E-11 pass in both Groq runs |
| PBI-10 | Streamlit page: chat, tool calls with their path, cart, Confirm and Cancel, outage switch | `app.py`, `src/app_logic.py`; G-01; `tests/test_app.py` |
| PBI-14 | 85 new unit tests; saved results | 239 tests pass; `SPRINT_2_UNIT_TESTS.md` |
| PBI-23 | Runner with MCP scenarios; Groq, Streamlit, and local Qwen results | `SPRINT_2_EVALUATION.md`. Groq: 18 Pass, 4 Partial, 0 Fail on both 2026-11-15 and 2026-11-18. Local Qwen in Colab: 8 Pass, 3 Partial, 0 Fail |

## Partially completed work

| Item | What is missing | Next action |
|---|---|---|
| PBI-21 corrective retry | Built and unit tested, but no Groq run had a refused tool call, so it was never used with a real model. | Keep watching for `model_retries` above 0 in the result files. Do not call it fixed before that. |
| E-03 answer | On Groq the answer no longer mentions soy (Pass in Sprint 1, Partial now). The safety answer is still correct. | PBI-22: decide the criterion, then change the prompt or the check. |
| Tool contract | `docs/CONTRACT.md` still has the status "draft, waiting for review". | Rui Zhao approves it. |

## Not completed or moved

| Item | Decision |
|---|---|
| PBI-22: E-03 and E-05 answer criteria | Not started. Stays in the Product Backlog. |
| PBI-13: RAG | Moved to "Later": the course puts RAG outside Sprint 2. |
| PBI-15 (past pickup times), PBI-20 (reserve stock) | Not selected. Next-sprint candidates. |

## External API status

The inventory API is a mock REST API that we wrote; it is not a real restaurant system. It works over HTTP in every scenario that needs stock (E-01, E-04, E-06, G-01). New in Sprint 2: `confirm_draft` on the MCP server calls it again before a confirmation. There is no open blocker.

## Scope decisions during the sprint

- **PBI-11 became smaller:** the MCP server exposes three new order tools instead of the six Sprint 1 tools. The six tools stayed direct calls, so the Sprint 1 scenarios could not break because of MCP.
- **Only the customer confirms:** the model has no tool for it. The Confirm button calls the MCP server.
- **RAG moved out** of Sprint 2.
- **A limit of 800 output tokens** was added after Groq refused nearly every request of the first evaluation run.

## Feedback

No external feedback yet.

## Changes to the Product Backlog

- PBI-21 stays open as Partial.
- PBI-22 now also covers E-03.
- New: PBI-24 (find drafts again after a page reload), PBI-25 (one long MCP connection).
- PBI-22 moves to Sprint 3, with Zongru Li as the owner.

## Scrum events

| Event | What happened |
|---|---|
| Sprint Planning | 2026-11-05, on Zoom and WeChat. The team set the Sprint Goal and selected PBI-21, PBI-12, PBI-11, PBI-10, PBI-14, PBI-23, and PBI-22: 25 story points in total, about 8 for each person. Scope choices: PBI-11 became smaller (8 → 5 points), RAG moved out, PBI-14 was widened to all project functions, and PBI-23 was added. Dependencies: the draft rules (PBI-12) came before the MCP server (PBI-11); the MCP client came before the Confirm and Cancel buttons on the page (PBI-10); the evaluation (PBI-23) came last. |
| Daily Scrum / check-ins | Once a day, in meetings on Zoom and messages on WeChat. One obstacle: on 2026-11-14 the first complete evaluation run failed in 21 of 22 runs with HTTP 429, because of Groq's output-token limit. The team limited each reply to 800 tokens, added more retries, and ran the evaluation again on 2026-11-15. |
| Sprint Review | 2026-11-18, on Zoom and WeChat. The team showed the three steps under "Increment shown" and the Groq and local Qwen results. Accepted: PBI-12, PBI-11, PBI-10, PBI-14, PBI-23. Not accepted: PBI-21 (Partial) and PBI-22 (To do). No external feedback. |
| Sprint Retrospective | 2026-11-18, on Zoom and WeChat. See below. |

## Retrospective

The team did the retrospective together. The list shows the team's shared view.

- **One practice that worked:** We marked an item Done only when a named test or evaluation result supported it. So we kept PBI-21 as Partial, although its unit tests pass, because no real Groq run used the retry.
- **One problem in the way of working:** Most of the work was still finished late. The page, the MCP server and client, and the tests were merged on 2026-11-15, and the local Qwen run and the Colab check were done on 2026-11-18, the last day of the sprint.
- **One specific improvement for the next sprint:** At Sprint Planning, give each task an owner, an estimate, and a due date, and merge each item as its own reviewed pull request by that date.

Sprint 1 improvement to check: "split the work into tasks with dates at Sprint Planning". We did it only in part. We split the work into tasks with owners and estimates, about 8 story points for each person, but we did not set due dates. As a result, the work was still concentrated at the end of the sprint.
