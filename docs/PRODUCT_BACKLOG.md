******# Product Backlog — Restaurant Order Agent

> The items are ordered by priority (top = next). Top items have detailed acceptance criteria; lower items stay short. The backlog changes after each Sprint Review. Changes are recorded at the end of this file.

- **Product Owner:** `[Name]`
- **Estimate unit:** story points (1, 2, 3, 5, 8)

## Sprint 1 items

| Order | ID | User story | Estimate | Acceptance criteria | Status |
|---|---|---|---|---|---|
| 1 | PBI-01 | As a customer, I want to search the menu by word, category, or maximum price, so that I find dishes quickly. | 2 | `search_menu` returns only items from the database that match all given filters. Prices are the database prices. An unknown word returns an empty list, not invented items. | To do |
| 2 | PBI-02 | As a customer, I want to get only menu items that match my diet, so that I do not read the whole menu. | 5 | `filter_dietary_options` returns items that have **all** requested labels, **none** of the excluded allergens, and are served on the current day. Example: vegan + gluten-free mains returns only the items with both labels in the database. Unknown labels are refused with a clear message. | To do |
| 3 | PBI-03 | As a customer with an allergy, I want to see a dish's ingredients and allergens, so that I can order safely. | 3 | `get_ingredients` returns the ingredients and allergens from the ingredient table. An unknown dish returns "not found". The agent does not guess allergens from the dish name. | To do |
| 4 | PBI-04 | As a customer, I want the agent to check live stock, so that I do not choose a sold-out dish. | 5 | A mock inventory REST API returns the portions left per item. `check_availability` reports sold-out items. If the API is not available (HTTP 503, timeout, or bad JSON), the tool returns a clear error and no invented stock value. | To do |
| 5 | PBI-05 | As a customer, I want an exact total and a budget check, so that I do not spend more than planned. | 3 | `calculate_total` adds integer cents from database prices. The total equals the manual sum of the database prices. Example: 2 × a 19.90 € dish = 39.80 €, reported as 9.80 € over a 30 € budget. | To do |
| 6 | PBI-06 | As a customer, I want the agent to prepare an order draft with a pickup time, so that I only need to confirm it. | 5 | `draft_order` saves a draft only when pickup hours, menu day, dietary labels, allergens, budget, and stock all pass. Otherwise it saves nothing and returns the list of problems. A saved draft has the status `awaiting_customer_confirmation`. No purchase is made. | To do |
| 7 | PBI-07 | As a customer, I want to write my request in normal language and get an answer, so that I do not need to use the tools myself. | 5 | In the notebook and the CLI, a request reaches Qwen on Groq. Qwen calls the tools, and the answer uses the tool results. The executor refuses unknown tools and invalid arguments. The loop stops after a maximum number of rounds and tool calls. The tool trace can be shown. | To do |
| 8 | PBI-08 | As the team, we want to run the same scenarios with Groq and with local Qwen3.5-4B in Colab, so that we can compare the two modes. | 3 | The local model uses the same tools and executor. The same scenarios run in both modes. The results are recorded in `SPRINT_1_EVALUATION.md`. | To do |
| 9 | PBI-09 | As the team, we want an assistant-level evaluation, so that we have evidence that the agent works. | 3 | At least 3 scenarios (planned: 8) cover a normal task, a database filter, an external API case, and failure cases. Each result is checked against database rows and API state and recorded as Pass, Partial, or Fail. | To do |

## Next-sprint candidates (Sprint 2)

| Order | ID | User story | Estimate | Acceptance criteria |
|---|---|---|---|---|
| 1 | PBI-10 | As a customer, I want a Streamlit ordering page with a chat and a cart, so that I can order without a notebook. | 8 | The chat sends requests to the agent. The cart shows the draft lines and the total from `calculate_total`. The tool trace can be expanded. The page starts with `streamlit run`. |
| 2 | PBI-11 | As a developer, I want the ordering tools served through an MCP server, so that any MCP client can use them. | 8 | An MCP client lists the six tools. The agent calls them through MCP. The Sprint 1 evaluation still passes. |
| 3 | PBI-12 | As a customer, I want to confirm or cancel my draft, so that I stay in control of the order. | 3 | The status changes only when the draft exists and has the status `awaiting_customer_confirmation`. No payment. |
| 4 | PBI-13 | As a customer, I want answers about allergen warnings, kitchen preparation policies, and FAQs, so that I can trust the answer. | 8 | RAG answers cite the retrieved document. A question that the documents do not cover gets "I do not know". |
| 5 | PBI-14 | As the team, we want unit tests for all tool functions, so that changes do not break the tools. | 3 | Tests cover the normal, empty, and error path of each tool. All tests pass before each merge. |
| 6 | PBI-15 | As a customer, I want pickup times in the past to be refused. | 2 | A past pickup time gives a clear reason and no draft. Tested with a fixed clock in the restaurant's time zone. |

## Later (not estimated yet)

| ID | Item |
|---|---|
| PBI-16 | Compare a single agent with menu-discovery, allergen-validation, and order-assembly agents (Sprint 3). |
| PBI-17 | Fine-tune a small Qwen model for structured order extraction: quantities, notes, pickup times (Sprint 3). |
| PBI-18 | Tests for out-of-stock items, budget overruns, and conflicting allergen tags (Sprint 3). |
| PBI-19 | Security tests: prompt injection in user requests and tool data, tool-argument abuse (Sprint 3). |
| PBI-20 | Reserve stock when the customer confirms a draft (mock API `POST` endpoint; still no payment). |
