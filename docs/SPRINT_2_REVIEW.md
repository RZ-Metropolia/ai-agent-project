# Sprint 2 Review — Restaurant Order Agent

> **To the team:** the technical sections are filled in from the code, tests, and evaluation. Everything in `[square brackets]` must come from you: dates, people, feedback, and the retrospective. Do not claim an event that did not happen.

- **Sprint:** 2 (`[start date]` to `[end date]`)
- **Team:** `[names and roles]`
- **Sprint Goal:** "A customer can order in a Streamlit page: the assistant prepares a draft with the Sprint 1 tools, and the customer sees, cancels, or confirms their own drafts through an MCP server."

## Was the Sprint Goal met?

**Mostly yes, on Groq.** In the Streamlit page, a request reaches Qwen, Qwen calls the Sprint 1 tools, and a draft appears in the cart. The assistant lists and cancels drafts through the MCP client and server, and the Confirm button confirms a draft through the same MCP server after a new stock check. Nothing is ordered or paid.

Not finished:

- The local Qwen comparison was not run for Sprint 2.
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
| PBI-23 (Groq part) | Runner with MCP scenarios; Groq and Streamlit results | `SPRINT_2_EVALUATION.md` |

## Partially completed work

| Item | What is missing | Next action |
|---|---|---|
| PBI-21 corrective retry | Built and unit tested, but no Groq run had a refused tool call, so it was never used with a real model. | Keep watching for `model_retries` above 0 in the result files. Do not call it fixed before that. |
| PBI-23 local comparison | The evaluation was not run with local Qwen in Colab. | `[who, when]` runs it and fills in the comparison table. |
| E-03 answer | On Groq the answer no longer mentions soy (Pass in Sprint 1, Partial now). The safety answer is still correct. | PBI-22: decide the criterion, then change the prompt or the check. |
| Tool contract | `docs/CONTRACT.md` still has the status "draft, waiting for review". | `[name]` approves it. |

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

`[Feedback from the Sprint Review: who said what, and what we will change. Write "No external feedback yet" if there was none.]`

## Changes to the Product Backlog

- PBI-21 stays open as Partial.
- PBI-22 now also covers E-03.
- New: PBI-24 (find drafts again after a page reload), PBI-25 (one long MCP connection).
- `[Any change from the review feedback]`

## Scrum events

| Event | What happened |
|---|---|
| Sprint Planning | `[date and method; the Sprint Goal; the selected PBIs; estimates; the scope choices above; dependencies]` |
| Daily Scrum / check-ins | `[real frequency and method; one obstacle, adjustment, or coordination decision — for example the Groq token limit]` |
| Sprint Review | `[date and method; what was shown; accepted and incomplete items; feedback]` |
| Sprint Retrospective | `[date and method]` See below. |

## Retrospective

`[Fill in together.]`

- **One practice that worked:** `[ ]`
- **One problem in the way of working:** `[ ]`
- **One specific improvement for the next sprint:** `[ ]`

Sprint 1 improvement to check: "split the work into tasks with dates at Sprint Planning". `[Did we do it? What happened?]`
