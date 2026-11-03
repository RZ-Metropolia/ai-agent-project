# Sprint 1 Backlog — Restaurant Order Agent

## Sprint Goal

**"A customer can ask in natural language for a pickup order that matches a diet and a budget, and the agent creates a verified order draft using only database and inventory-API data."**

- **Sprint dates:** `[start date]` – `[review date]`
- **Sprint Planning:** `[date, duration, who attended]`

## Roles

| Role | Person | What this person did in this sprint |
|---|---|---|
| Product Owner | `[Person A]` | `[One prioritization or clarification decision]` |
| Scrum Master | `[Person B]` | `[How this person helped expose or remove a blocker]` |
| Developers | `[Person A]`, `[Person B]` | Person A: data, inventory API, and order rules. Person B: tools layer, agent loops, interaction, and evaluation. |

### How technical work was shared

The work is split at `tools.py`.

- **Person A** builds everything below it, in plain Python with no model: the SQLite database, the mock inventory API and its client, and the order rules.
- **Person B** builds everything above it: the tool wrappers and executor, the Groq and local Qwen loops, the notebook and CLI, and the evaluation runner.

On day 1, both people agree on the function signatures and return dictionaries of the six tools. Person B starts with stub tools that return the agreed examples. Both people review each other's code. Each person writes at least one evaluation scenario.

## Selected items and tasks

| Product Backlog item | Sprint task | Owner(s) | Estimate | Status | Acceptance evidence |
|---|---|---|---|---|---|
| — | Agree on the tool contract: signatures and example return values | A, B | 1 h | To do | `docs/CONTRACT.md` or a section in the README |
| PBI-01, PBI-02 | Create the SQLite schema and synthetic seed data (menu items, ingredients, labels, serving days) | A | 4 h | To do | Database creates from the seed file; row counts match the seed |
| PBI-01 | Implement `search_menu` (word, category, maximum price) | A | 1 h | To do | Results match a direct SQL query |
| PBI-02 | Implement `filter_dietary_options` (all labels, no excluded allergens, served today) | A | 3 h | To do | Vegan + gluten-free mains match a direct SQL query |
| PBI-03 | Implement `get_ingredients` with allergens | A | 2 h | To do | Allergens match the ingredient table; unknown dish returns "not found" |
| PBI-04 | Build the mock inventory REST API with an outage switch | A | 3 h | To do | `GET /inventory` returns portions; outage mode returns HTTP 503 |
| PBI-04 | Build the API client with timeout, HTTP-error, and JSON checks; implement `check_availability` | A | 3 h | To do | Outage gives a clear error; evaluation E-04, E-06 |
| PBI-05 | Implement `calculate_total` with integer cents and a budget check | A | 2 h | To do | 2 × a 19.90 € dish = 39.80 €; evaluation E-07 |
| PBI-06 | Implement `draft_order` with all checks; fail closed when the API is down | A | 4 h | To do | Each refused case saves no draft; evaluation E-01, E-04, E-06, E-07, E-08 |
| PBI-07 | Wrap the six functions as LangChain tools with Pydantic schemas; build the registry and the executor | B | 3 h | To do | Unknown tool and invalid arguments are refused |
| PBI-07 | Write the system prompt and the Groq tool-calling loop with limits and a trace | B | 4 h | To do | Notebook demo A shows the tool calls and the answer |
| PBI-07 | Build the CLI chat and the Colab demo notebook | B | 3 h | To do | Demo runs from the README instructions |
| PBI-08 | Build the local Qwen3.5-4B loop (4-bit, Colab GPU) with the XML tool-call parser | B | 3 h | To do | Same scenarios run in local mode |
| PBI-09 | Write the expected results for the evaluation scenarios from the data | A | 2 h | To do | Expected column in `SPRINT_1_EVALUATION.md` |
| PBI-09 | Build the evaluation runner; run and record all scenarios in both modes | B | 4 h | To do | `docs/SPRINT_1_EVALUATION.md` |
| — | Product Vision, Product Backlog | A | 2 h | To do | Files in the repository |
| — | README, Sprint Backlog, Review and retrospective, slides | B | 4 h | To do | Files in the repository |
