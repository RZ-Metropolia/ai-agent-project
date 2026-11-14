# Product Backlog — Restaurant Order Agent

> The items are ordered by priority (top = next). Top items have detailed acceptance criteria; lower items stay short. The backlog changes after each Sprint Review. Changes are recorded at the end of this file.

- **Product Owner:** Zongru Li `[check: update if the role changed in Sprint 2]`
- **Estimate unit:** story points (1, 2, 3, 5, 8)

## Sprint 2 items

| Order | ID | User story | Estimate | Acceptance criteria | Status |
|---|---|---|---|---|---|
| 1 | PBI-21 | As a customer, I want an answer even when Groq refuses a tool call, so that my request does not just fail. | 2 | After a refused tool call, the loop retries with a note that names the correct tools. E-01 and E-07 pass in both Groq runs. The customer sees no raw error text. | **Partial.** The retry and the friendly error are built and unit tested. E-01 and E-07 passed in both runs, but no call was refused in those runs, so the retry was never used with a real model. |
| 2 | PBI-12 | As a customer, I want to confirm or cancel my draft, so that I stay in control of the order. | 3 | The status changes only when the draft exists, belongs to my session, and has the status `awaiting_customer_confirmation`. Stock is checked again before a confirmation. No payment. Only the customer can confirm. | Done. `tests/test_orders.py`; G-01. |
| 3 | PBI-11 | As a developer, I want the order-draft tools served through an MCP server, so that the assistant and the page use them through one MCP client. | 5 | An MCP server exposes `list_drafts`, `cancel_draft`, and `confirm_draft`. An MCP client starts it and calls it. The assistant uses `list_drafts` and `cancel_draft` in a user task. An MCP failure gives a clear answer. The Sprint 1 scenarios still work. | Done. E-09, E-10, E-11; `tests/test_mcp_server.py`, `tests/test_mcp_client.py`. |
| 4 | PBI-10 | As a customer, I want a Streamlit ordering page with a chat and a cart, so that I can order without a notebook. | 8 | The chat sends requests to the agent. The cart shows the draft lines and the total from the tools. Confirm and Cancel work. The tool calls of each answer can be opened. The page starts with `streamlit run app.py`. | Done. G-01; `tests/test_app.py`. |
| 5 | PBI-14 | As the team, we want unit tests for all project functions, so that changes do not break them. | 3 | Tests cover the normal, empty, and error path of each tool, the draft rules, the MCP server functions, the MCP client, and the page logic. The results are saved in the repository. | Done. 239 tests pass; `SPRINT_2_UNIT_TESTS.md`. |
| 6 | PBI-23 | As the team, we want a Sprint 2 evaluation, so that we know the old tasks still work and the MCP path works. | 3 | The Sprint 1 scenarios run again. At least one MCP success, one MCP edge or failure, and one Streamlit scenario are recorded. Groq and local Qwen are compared. | **Partial.** Groq and Streamlit are recorded. Local Qwen is not run yet. |
| 7 | PBI-22 | As the team, we want clear criteria for the E-03 and E-05 answers, so that "Partial" has a decision behind it. | 1 | The team decides whether the answer must name the second allergen (E-03) and the nearest dish (E-05). The criteria or the prompt are updated. | To do. |

## Next-sprint candidates

| Order | ID | User story | Estimate | Acceptance criteria |
|---|---|---|---|---|
| 1 | PBI-15 | As a customer, I want pickup times in the past to be refused. | 2 | A past pickup time gives a clear reason and no draft. Tested with a fixed clock in the restaurant's time zone. |
| 2 | PBI-20 | As a customer, I want my confirmed order to hold its portions, so that the dish is not sold to someone else. | 5 | Confirming reserves stock through a mock API `POST` endpoint. Two sessions cannot both confirm the last portion. Still no payment. |
| 3 | PBI-24 | As a customer, I want to find my drafts again after I reload the page. | 3 | A session survives a page reload. No accounts and no personal data. |
| 4 | PBI-19 | As the team, we want security tests, so that we know what a hostile request can do. | 5 | Prompt injection in user requests and in tool data, and tool-argument abuse, are tested and recorded. |

## Later (not estimated yet)

| ID | Item |
|---|---|
| PBI-13 | Answers about allergen warnings, kitchen preparation policies, and FAQs, with RAG and cited documents. Moved out of Sprint 2: the course puts RAG outside Sprint 2. |
| PBI-16 | Compare a single agent with menu-discovery, allergen-validation, and order-assembly agents (Sprint 3). |
| PBI-17 | Fine-tune a small Qwen model for structured order extraction: quantities, notes, pickup times (Sprint 3). |
| PBI-18 | Tests for out-of-stock items, budget overruns, and conflicting allergen tags (Sprint 3). |
| PBI-25 | One long MCP connection instead of a new server process for each call, to save about one second per call. |

## Done in Sprint 1

| ID | User story | Estimate | Acceptance criteria | Status |
|---|---|---|---|---|
| PBI-01 | As a customer, I want to search the menu by word, category, or maximum price, so that I find dishes quickly. | 2 | `search_menu` returns only items from the database that match all given filters. Prices are the database prices. An unknown word returns an empty list, not invented items. | Done |
| PBI-02 | As a customer, I want to get only menu items that match my diet, so that I do not read the whole menu. | 5 | `filter_dietary_options` returns items that have **all** requested labels, **none** of the excluded allergens, and are served on the current day. Example: vegan + gluten-free mains returns only the items with both labels in the database. Unknown labels are refused with a clear message. | Done |
| PBI-03 | As a customer with an allergy, I want to see a dish's ingredients and allergens, so that I can order safely. | 3 | `get_ingredients` returns the ingredients and allergens from the ingredient table. An unknown dish returns "not found". The agent does not guess allergens from the dish name. | Done |
| PBI-04 | As a customer, I want the agent to check live stock, so that I do not choose a sold-out dish. | 5 | A mock inventory REST API returns the portions left per item. `check_availability` reports sold-out items. If the API is not available (HTTP 503, timeout, or bad JSON), the tool returns a clear error and no invented stock value. | Done |
| PBI-05 | As a customer, I want an exact total and a budget check, so that I do not spend more than planned. | 3 | `calculate_total` adds integer cents from database prices. The total equals the manual sum of the database prices. Example: 2 × a 19.90 € dish = 39.80 €, reported as 9.80 € over a 30 € budget. | Done |
| PBI-06 | As a customer, I want the agent to prepare an order draft with a pickup time, so that I only need to confirm it. | 5 | `draft_order` saves a draft only when pickup hours, menu day, dietary labels, allergens, budget, and stock all pass. Otherwise it saves nothing and returns the list of problems. A saved draft has the status `awaiting_customer_confirmation`. No purchase is made. | Done |
| PBI-07 | As a customer, I want to write my request in normal language and get an answer, so that I do not need to use the tools myself. | 5 | In the notebook and the CLI, a request reaches Qwen on Groq. Qwen calls the tools, and the answer uses the tool results. The executor refuses unknown tools and invalid arguments. The loop stops after a maximum number of rounds and tool calls. The tool trace can be shown. | Done. 2 of 16 Groq runs failed in Sprint 1: see PBI-21. |
| PBI-08 | As the team, we want to run the same scenarios with Groq and with local Qwen3.5-4B in Colab, so that we can compare the two modes. | 3 | The local model uses the same tools and executor. The same scenarios run in both modes. The results are recorded in `SPRINT_1_EVALUATION.md`. | Done |
| PBI-09 | As the team, we want an assistant-level evaluation, so that we have evidence that the agent works. | 3 | At least 3 scenarios (planned: 8) cover a normal task, a database filter, an external API case, and failure cases. Each result is checked against database rows and API state and recorded as Pass, Partial, or Fail. | Done |

## Changes to this backlog

| Date | Change | Reason |
|---|---|---|
| 2026-11-04 | New: PBI-21 (corrective retry). New: PBI-22 (answer criteria; at first only for E-05). | Sprint 1 Review: 2 of 16 Groq runs failed with refused tool calls; E-05 was Partial in both modes. |
| 2026-11-04 | PBI-12 (confirm or cancel) confirmed for Sprint 2. | Sprint 1 Review. |
| Sprint 2 Planning `[date]` | PBI-13 (RAG) moved from Sprint 2 to "Later". | The course puts RAG outside Sprint 2. |
| Sprint 2 Planning `[date]` | PBI-11 changed: the MCP server exposes three new order-draft tools, not the six Sprint 1 tools. Estimate 8 → 5. | The course asks for at least one useful MCP tool and says that not every tool must move. Keeping the six tools as direct calls avoids regressions. |
| Sprint 2 Planning `[date]` | PBI-14 widened from "tool functions" to all project functions, with saved results. New: PBI-23 (Sprint 2 evaluation). | Sprint 2 course requirements. |
| 2026-11-15 | PBI-22 widened to E-03. New: PBI-24 (sessions after a reload), PBI-25 (one long MCP connection). | Sprint 2 evaluation: E-03 became Partial on Groq. Limits found while building the page and the MCP client. |
| 2026-11-15 | Sprint 1 statuses set to Done; Product Owner name added. | They were still "To do" and `[Name]` after Sprint 1. |
