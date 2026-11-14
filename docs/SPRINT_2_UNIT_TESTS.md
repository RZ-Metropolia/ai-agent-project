# Sprint 2 Function Unit Tests — Restaurant Order Agent

Unit tests check our own functions in isolation. They are separate from the assistant evaluation in [SPRINT_2_EVALUATION.md](SPRINT_2_EVALUATION.md), which uses a real model from request to answer.

## How to run

```bash
python -m unittest discover tests
```

The tests need no API key and no GPU. Each test builds a fresh database in a temporary folder.

## Test run

| Item | Value |
|---|---|
| Date | 2026-11-14 |
| Environment | Python 3.14.6, Windows 11, `mcp` 1.30.0, `streamlit` 1.67.0 |
| Result | **239 tests ran, 239 passed, 0 failed** |
| Full output | [test_results/sprint2_unit_tests.txt](test_results/sprint2_unit_tests.txt) |

Sprint 1 ended with 154 tests. Sprint 2 added 85 and changed 2 (see "Changed Sprint 1 tests").

## What replaces the real services

| Real part | In the tests | Why |
|---|---|---|
| Qwen (Groq or local) | `ScriptedModel`: plays back fixed tool calls and answers | The model is not deterministic and needs a key or a GPU. |
| Inventory API | `FakeInventory`, `httpx.MockTransport`, or the real mock API on a free port | To force stock values, HTTP errors, timeouts, and bad JSON. |
| MCP server | Real server process over stdio in `RealServerTests`; `unittest.mock.patch` elsewhere | To test both the real connection and the client's own logic. |
| Streamlit | `streamlit.testing.v1.AppTest` runs the real `app.py` | To click buttons and read the page without a browser. |

## Test files

| File | Tests | Component |
|---|---|---|
| `tests/test_db.py` | 29 | Schema, constraints, seed data, and the data that the evaluation relies on |
| `tests/test_inventory.py` | 17 | Mock inventory API and the API client (adapter) |
| `tests/test_tools.py` | 81 | The six direct tools, and E-01 to E-08 at tool level |
| `tests/test_orders.py` | 23 | **New.** Sessions, and the list, cancel, and confirm rules |
| `tests/test_mcp_server.py` | 10 | **New.** The functions that the MCP server exposes |
| `tests/test_mcp_client.py` | 17 | **New.** MCP result handling, server settings, and real stdio calls |
| `tests/test_agent.py` | 35 | Executor, agent loop, retry, XML parser, and the evaluation checks |
| `tests/test_app_logic.py` | 18 | **New.** The logic behind the Streamlit page |
| `tests/test_app.py` | 9 | **New.** The Streamlit page itself |

## Evidence by area

The course lists six areas. Each row is one test from the run above; "Actual result" is what the test observed.

### Data insertion, retrieval, filtering, and validation

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| `init_db` | Build from `seed.json` | Row counts equal the seed | Equal for all 10 tables | Pass |
| `filter_dietary_options` | vegetarian, without milk | The same rows as a direct SQL query | Same rows | Pass |
| `filter_dietary_options` | vegan dessert, at most 4 € | Empty list | Empty list | Pass |
| `filter_dietary_options` | Allergen `sesamee` (typo) | Refused with `unknown_allergen`, no items | `unknown_allergen`, no items | Pass |
| `draft_order` | Valid order in session `alice` | One row with `session_id = alice` | Stored with `alice` | Pass |
| `draft_order` | The same order in two sessions | Two separate drafts | Two drafts | Pass |
| `list_drafts` | A session without drafts | Empty list | Empty list | Pass |
| `list_drafts` | A menu price changes after the draft | The draft keeps its old price | 3.50 € and 16.00 € unchanged | Pass |

### Generic functions and API tool adapters

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| `calculate_total` | 2 × Grilled Salmon, budget 30 € | 39.80 €, 9.80 € over | 39.80 €, 9.80 € over | Pass |
| `InventoryClient.get_portions` | Valid response | `{1: 8, 2: 0}` | `{1: 8, 2: 0}` | Pass |
| `InventoryClient.get_portions` | Mocked HTTP 404, 500, 503 | `InventoryUnavailable`, no stock value | Raised with the status code | Pass |
| `InventoryClient.get_portions` | Mocked timeout; slow real server | `InventoryUnavailable` after the timeout | Raised in under 0.9 s | Pass |
| `InventoryClient.get_portions` | Bad JSON, negative or text portions | `InventoryUnavailable` | Raised for all 10 cases | Pass |
| `check_availability` | A dish missing from the API answer | Error, not "available" | `inventory_unavailable` | Pass |

### Tool input validation and result processing

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| `execute_tool` | Unknown tool `pay_order` | Refused | `unknown_tool` | Pass |
| `execute_tool` | Model sends `service_date` or `session_id` | Refused: the model cannot set the context | `invalid_argument` | Pass |
| `execute_tool` | `confirm_draft` from the model | Refused: only the customer confirms | `unknown_tool` | Pass |
| `execute_tool` | `cancel_draft` with draft 0, -1, "one", 1.5 | Refused before any MCP call | `invalid_argument`, no MCP call | Pass |
| `run_agent` | Groq refuses a tool call once | The retry adds a note with the tool names; the note is not kept | Note present on the retry only | Pass |
| `run_agent` | Model error | Friendly answer; details only in `error` | No technical text in the answer | Pass |
| `run_agent` | Direct and MCP tool calls | Trace marks `direct` and `mcp` | Marked correctly | Pass |

### Functions exposed by the MCP server

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| MCP server | List the tools | `list_drafts`, `cancel_draft`, `confirm_draft`, each needing `session_id` | As expected | Pass |
| `cancel_draft` | Own awaiting draft | Status `cancelled` | `cancelled` in the database | Pass |
| `cancel_draft` | Draft 99; another session's draft | `draft_not_found`, nothing changed | `draft_not_found`, unchanged | Pass |
| `cancel_draft` | Already cancelled or confirmed | `draft_not_awaiting` | `draft_not_awaiting` | Pass |
| `confirm_draft` | Own awaiting draft, stock available | Status `confirmed`, message says no payment | `confirmed`, "No payment was made" | Pass |
| `confirm_draft` | Dish sold out since the draft | `confirmation_refused` with `sold_out` | Refused, still awaiting | Pass |
| `confirm_draft` | Inventory API returns HTTP 503 | Refused (fail closed) | `inventory_unavailable`, still awaiting | Pass |
| `confirm_draft` | Draft from another service day | `draft_expired` | `draft_expired` | Pass |
| Server tools | Invalid session IDs (empty, spaces, SQL text, too long) | `invalid_argument`, nothing changed | Refused for all 7 cases | Pass |

### MCP client-side processing and wrappers

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| `parse_result` | Tool result as JSON text | The same dictionary | Same dictionary | Pass |
| `parse_result` | MCP error result | `mcp_tool_error` with the server's message | As expected | Pass |
| `parse_result` | Not JSON, a list, no `ok`, no text | `mcp_bad_response` | For all 5 cases | Pass |
| `server_parameters` | A context with a database and service day | The server gets the same values in its environment | As expected | Pass |
| `list_drafts`, `cancel_draft`, `confirm_draft` | A context with session `alice` | `session_id` is sent from the context | As expected | Pass |
| `call_tool` | Real server: list, cancel, confirm | The database changes | `cancelled`, `confirmed` | Pass |
| `call_tool` | Real server: text as draft number; unknown tool | `mcp_tool_error`, nothing changed | As expected | Pass |
| `call_tool` | The server cannot start, or exits at once | `mcp_unavailable` | `mcp_unavailable` | Pass |
| `call_tool` | The server never answers | `mcp_unavailable` after the timeout | `mcp_unavailable` | Pass |
| `call_tool` | Called inside a running event loop (notebook) | Works | Works | Pass |

### Business logic called from the Streamlit interface

| Function/component | Test input or condition | Expected result | Actual result | Status |
|---|---|---|---|---|
| `load_model` | No `GROQ_API_KEY` | No model, and a message that says what to do | As expected | Pass |
| `ask` | Two requests in a row | The second request gets the history of the first | 6 messages kept | Pass |
| `trace_rows` | A direct call and a failed MCP call | Rows with "Python tool" / "MCP server" and the outcome | As expected | Pass |
| `load_cart` | Three drafts with different statuses | Newest first; only the awaiting draft can be changed | As expected | Pass |
| `load_cart` | MCP server unavailable | No drafts and a clear message | As expected | Pass |
| `change_draft` | Refused confirmation with two problems | One message that lists both | As expected | Pass |
| `app.py` | A request that saves a draft | Answer, "Tool calls (1)", and the draft in the sidebar | As expected | Pass |
| `app.py` | Click Confirm / Cancel | Status changes in the database through MCP; buttons disappear | `confirmed` / `cancelled` | Pass |
| `app.py` | Outage switch on, then Confirm | Error shown; the draft still awaits; buttons stay | As expected | Pass |

## Changed Sprint 1 tests

| Test | Change | Reason |
|---|---|---|
| `test_registry_has_the_six_tools` | Now expects six direct tools and two MCP tools | The model has two new tools. |
| `test_model_error_gives_an_answer_instead_of_a_crash` | Checks `result.error` for the details, and that the answer has none | The customer no longer sees raw error text. |

## Not unit tested, and why

| Part | Reason | Other validation |
|---|---|---|
| `groq_model` and `LocalQwen.invoke` | They need a Groq key or a GPU. | The assistant evaluation runs both models. |
| `src/cli.py` | It is an input loop around tested functions. | Run by hand. |
| The page layout in a real browser | `AppTest` checks elements and state, not how the page looks. | Checked by hand in a browser; see scenario G-01 in the evaluation. |
| Colab | The tests ran on Windows only. | The notebook must be run in Colab before the review. |
