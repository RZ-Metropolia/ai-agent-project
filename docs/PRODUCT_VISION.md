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

## Rules the product must follow

> Project 7 says: "Never execute live purchases. Dietary and allergen validations must depend strictly on tool data, not LLM guesses."

- The agent only prepares a draft with the status `awaiting_customer_confirmation`. No tool can order or pay.
- Allergen answers come only from the ingredient table, never from the model.
- The model never calculates prices. `calculate_total` adds integer cents from database prices.
- `draft_order` checks pickup hours, menu day, dietary labels, allergens, budget, and stock again before it saves a draft.
- If the inventory API is not available, `draft_order` refuses to create a draft (it fails closed).
- The model can call only the six approved tools, with validated arguments.

## Product roadmap

| Sprint | Course theme | Our product goal |
|---|---|---|
| Sprint 1 | Notebook assistant: filter by dietary tags, check availability through an API, compute prices deterministically, test in Groq and local Colab modes | A notebook and CLI agent that creates verified order drafts from database and API data only. |
| Sprint 2 | Streamlit ordering app with a cart; ordering tools through MCP; RAG over allergen warnings, kitchen policies, and FAQs | A Streamlit ordering page with a cart, the tools served through MCP, cited answers about allergen warnings and FAQs, and unit tests. |
| Sprint 3 | Menu-discovery, allergen-validation, and order-assembly agents; fine-tuning for structured order extraction; tests for out-of-stock items, budget overruns, and conflicting allergen tags | A comparison of a single agent and a multi-agent design, a fine-tuned order extractor, and systematic security and edge-case tests. |

## Success measures

- Every evaluation scenario passes in both of its 2 repeated Groq runs.
- No evaluation run creates an unsafe draft (a draft that breaks a dietary, allergen, stock, budget, or pickup-time rule).
- Every price, ingredient, and stock value in an answer can be traced to a tool result.
