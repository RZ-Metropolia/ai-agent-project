# Product Vision

- **Product name:** Restaurant Order Agent
- **Team:** `Group 1`

## Vision statement

**For** pickup customers who have dietary needs, allergies, or a budget, who spend time reading menus and asking staff about ingredients, stock, and prices, the Restaurant Order Agent is a tool-using AI assistant that finds suitable menu items, checks live stock, calculates exact totals, and prepares an order draft. Unlike a general chatbot, our product answers only from the restaurant's own database and inventory system, and it never places or pays for an order.

## Target users

| User | Need |
|---|---|
| **Primary:** pickup customers with dietary needs (vegetarian, vegan, gluten-free, dairy-free), allergies, or a budget | Find food that matches the diet, avoid allergens, stay within the budget, and pick up at a chosen time. |
| **Secondary:** restaurant staff | Receive complete, checked order drafts and answer fewer repeated menu questions. |

## Problem

- Menus show dietary labels in different ways. Customers often must ask staff about allergens.
- Stock changes during the day. A customer can choose a dish that is already sold out.
- Customers add the prices themselves and can go over their budget.
- A general LLM can invent ingredients, prices, or "safe" claims. For allergies, this is dangerous.

## Value

- Answers come only from tool data: the menu database, the inventory API, and a deterministic price calculation.
- Fewer failed orders: the agent finds sold-out items, invalid pickup times, and budget overruns before it creates a draft.
- The customer stays in control: the agent only prepares a draft, and the customer confirms it.

## Why a tool-using AI assistant

The LLM is good at understanding a request in natural language, for example "a cheap vegan lunch without nuts", and at choosing the correct tools and arguments. The facts (prices, ingredients, allergens, stock) belong to the restaurant and change. Python code is better for exact filtering, arithmetic, and safety checks. The product uses the LLM for understanding and the tools for every fact.

## First-version scope (Sprint 1)

**Representative user request:** *"Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros."*

**In scope**

- One end-to-end workflow: request → dietary and allergen filter → stock check → total and budget check → order draft.
- Qwen through Groq (`qwen/qwen3.8-27b`, main model) and local Qwen3.5-4B in Colab (comparison).
- Six tools: `search_menu`, `get_ingredients`, `filter_dietary_options`, `check_availability`, `calculate_total`, `draft_order`.
- SQLite database with menu items, ingredients, dietary labels, daily availability, draft orders, and order items. Synthetic sample data.
- Mock inventory REST API with error handling (sold-out item, service outage).
- Interaction through a Colab notebook and a command-line chat.
- Assistant-level evaluation with eight scenarios.

**Out of scope for Sprint 1**

- RAG, MCP, multi-agent design, and fine-tuning: the course puts them outside Sprint 1.
- Streamlit GUI: optional in Sprint 1; planned for Sprint 2.
- Payment, sending orders to the kitchen, and user accounts: not needed to show the first workflow, and payment is not allowed.

## Second-version scope (Sprint 2)

Sprint 2 keeps everything from Sprint 1 and adds one new workflow: **the customer sees, confirms, or cancels the drafts of their own session.**

**Representative user requests:** the Sprint 1 request above in the Streamlit page, then *"Please cancel my draft."* or a click on **Confirm**.

**In scope**

- A Streamlit page with a chat, a cart of drafts, Confirm and Cancel buttons, and the tool calls of each answer.
- An MCP server with three order tools (`list_drafts`, `cancel_draft`, `confirm_draft`) and an MCP client inside the assistant. The six Sprint 1 tools stay direct Python calls.
- Customer sessions: a draft belongs to one session.
- A corrective retry for tool calls that Groq refuses (from the Sprint 1 evaluation).
- Function unit tests with saved results, and an evaluation with Sprint 1 regression scenarios and MCP scenarios.

**Out of scope for Sprint 2**

- RAG, multi-agent design, and fine-tuning: the course puts them outside Sprint 2. Our first roadmap had RAG in Sprint 2, so PBI-13 moved to a later sprint.
- All six Sprint 1 tools through MCP: the course does not ask for it, and it would risk regressions.
- Payment, sending orders to the kitchen, and user accounts.

## Rules the product must follow

> Project 7 says: "Never execute live purchases. Dietary and allergen validations must depend strictly on tool data, not LLM guesses."

- The agent only prepares a draft with the status `awaiting_customer_confirmation`. No tool can order or pay.
- Allergen answers come only from the ingredient table, never from the model.
- The model never calculates prices. `calculate_total` adds integer cents from database prices.
- `draft_order` checks pickup hours, menu day, dietary labels, allergens, budget, and stock again before it saves a draft.
- If the inventory API is not available, `draft_order` refuses to create a draft (it fails closed).
- The model can call only the approved tools, with validated arguments: six in Sprint 1, plus `list_drafts` and `cancel_draft` since Sprint 2.
- Only the customer can confirm a draft, with the Confirm button. The model has no tool for it. Confirming changes the status and never pays.
- A session can see and change only its own drafts.
- Before a draft is confirmed, the stock is checked again. If the inventory API is not available, the confirmation is refused.

## Product roadmap

| Sprint | Course theme | Our product goal |
|---|---|---|
| Sprint 1 | Notebook assistant: filter by dietary tags, check availability through an API, compute prices deterministically, test in Groq and local Colab modes | A notebook and CLI agent that creates verified order drafts from database and API data only. |
| Sprint 2 | Keep the Sprint 1 product; add an MCP server and client, a Streamlit GUI, and function unit tests | A Streamlit ordering page with a cart, order-draft tools served through MCP, confirm and cancel for drafts, and unit tests with saved results. |
| Sprint 3 | Menu-discovery, allergen-validation, and order-assembly agents; fine-tuning for structured order extraction; tests for out-of-stock items, budget overruns, and conflicting allergen tags; RAG, if the course puts it in scope | A comparison of a single agent and a multi-agent design, a fine-tuned order extractor, systematic security and edge-case tests, and cited answers about allergen warnings and FAQs. |

The Sprint 2 row changed after the course published its Sprint 2 requirements: RAG moved out, and the MCP scope became three new order tools instead of the six existing tools.

## Success measures

- Every evaluation scenario passes in both of its 2 repeated Groq runs.
- No evaluation run creates an unsafe draft (a draft that breaks a dietary, allergen, stock, budget, or pickup-time rule).
- Every price, ingredient, and stock value in an answer can be traced to a tool result.
