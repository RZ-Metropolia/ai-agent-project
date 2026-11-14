# Restaurant Order Agent

A tool-using AI assistant for restaurant pickup orders. A customer writes a request in normal language, for example *"a vegetarian main and a drink for at most 20 euros, pickup at 18:30"*. Qwen chooses tools, and the tools answer from the menu database and the inventory API. The agent saves only an order draft, and the customer confirms or cancels it. Nothing is ever ordered or paid.

**The user problem:** pickup customers with a diet, an allergy, or a budget must check labels, allergens, stock, and prices themselves. A general chatbot can invent these facts.

| | What the product does |
|---|---|
| **Sprint 1 baseline** | A Qwen agent with six Python tools, a SQLite menu database, and a mock inventory REST API. It runs in a command-line chat and a Colab notebook, with Groq or a local Qwen model. |
| **Sprint 2 increment** | A Streamlit page with a chat and a cart. An MCP server with three order tools, and an MCP client inside the assistant. Customer sessions, confirm and cancel for drafts, a corrective retry for refused Groq tool calls, more unit tests, and a new evaluation. |

See [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md), [docs/PRODUCT_BACKLOG.md](docs/PRODUCT_BACKLOG.md), and [docs/SPRINT_2_BACKLOG.md](docs/SPRINT_2_BACKLOG.md).

## How the parts fit together

```text
Streamlit page (app.py)  /  CLI  /  Colab notebook
        |
   Agent loop (src/agent.py)  <->  Qwen (Groq, or local in Colab)
        |
   Executor (src/agent_tools.py): only the 8 known tools, checked arguments
        |
        +-- 6 direct Python tools (src/tools.py) --> SQLite, inventory REST API
        |
        +-- 2 MCP tools --> MCP client (src/mcp_client) --stdio--> MCP server (src/mcp_server)
                                                                     --> src/orders.py --> SQLite, inventory REST API
```

The Confirm and Cancel buttons on the page also call the MCP server through the MCP client.

## Qwen models

| Mode | Model | Where it runs | Configuration |
|---|---|---|---|
| Groq | `qwen/qwen3.8-27b` | Groq cloud | `GROQ_API_KEY` in `.env` or a Colab secret |
| Local | `Qwen/Qwen3.5-4B`, 4-bit (NF4) | Colab GPU | none |

The Streamlit page uses Groq mode. Both modes use the same loop, tools, and executor. The comparison is in [docs/SPRINT_2_EVALUATION.md](docs/SPRINT_2_EVALUATION.md).

## Project layout

| Path | Contents |
|---|---|
| `app.py` | The Streamlit page. It only draws the page. |
| `src/app_logic.py` | The logic behind the page: sessions, requests, cart, confirm, cancel. |
| `src/agent.py` | The system prompt and the tool-calling loop, with limits, a retry, and a tool trace. |
| `src/agent_tools.py` | LangChain wrappers with Pydantic schemas, and the executor. |
| `src/tools.py` | The six direct tools. Arguments and results: [docs/CONTRACT.md](docs/CONTRACT.md). |
| `src/orders.py` | The draft rules: list, confirm, cancel. |
| `src/mcp_server/` | The MCP server. It exposes `list_drafts`, `cancel_draft`, and `confirm_draft`. |
| `src/mcp_client/` | The MCP client. It starts the server over stdio and calls its tools. |
| `src/local_model.py` | Local Qwen3.5-4B and the parser for its XML tool calls. |
| `src/cli.py` | Command-line chat. |
| `src/evaluation.py` | The evaluation runner for scenarios E-01 to E-11. |
| `src/db.py`, `data/` | SQLite schema and synthetic seed data. |
| `src/inventory_api.py`, `src/inventory_client.py` | Mock inventory REST API and its client. |
| `notebooks/demo.ipynb` | Colab demo: Groq mode, local mode, and the evaluation. |
| `tests/` | Function unit tests. |

## Setup

You need Python 3.11 or later and a free Groq API key from https://console.groq.com.

1. Create a virtual environment and install the packages:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`, and set `GROQ_API_KEY` in `.env`. Never commit `.env`.
3. Optional: set `SERVICE_DATE=2026-11-06` in `.env`. This is the Friday that the evaluation uses, so the page then shows the same menu. Without it, the service day is today.

The database is built from `data/seed.json` on the first start. To build a fresh one, and delete all drafts, run `python -m src.db`. A database from Sprint 1 is rebuilt automatically, because drafts now need a session.

## Start the application

One command starts everything:

```bash
streamlit run app.py
```

There is no start order to remember:

- **Inventory API:** the page starts it in the background.
- **MCP client:** it is part of the application (`src/mcp_client`).
- **MCP server:** the MCP client starts it as a child process over stdio each time it calls a tool, and stops it after the call.

To start the MCP server by hand, for example for an MCP inspector, run `python -m src.mcp_server`. It waits for MCP messages on stdin.

### What the MCP server exposes

| MCP tool | What it does | Who calls it |
|---|---|---|
| `list_drafts` | Lists the drafts of one customer session | The assistant, and the cart on the page |
| `cancel_draft` | Cancels a draft that waits for confirmation | The assistant, and the Cancel button |
| `confirm_draft` | Checks live stock again, then confirms the draft. It never pays. | Only the Confirm button |

The model has no tool to confirm a draft, so only the customer can confirm.

**A request that shows the MCP path:** first ask *"Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink, with a total of at most 20 euros."* Then ask *"Please cancel my draft."* Open **Tool calls** under the answer: `list_drafts` and `cancel_draft` are marked **MCP server**, and the draft in the sidebar changes to **Cancelled**.

### Other ways to run it

```bash
python -m src.cli --trace          # command-line chat; --trace shows each tool call
```

For Colab: open `notebooks/demo.ipynb`, add `GROQ_API_KEY` as a Colab secret, and select **Runtime → Change runtime type → T4 GPU** for local mode. Run the cells one at a time.

## Tests

```bash
python -m unittest discover tests
```

The tests need no API key and no GPU. A scripted fake model replaces Qwen. The tests for the MCP client start the real MCP server, and the tests in `tests/test_app.py` run the real Streamlit page.

Results: [docs/SPRINT_2_UNIT_TESTS.md](docs/SPRINT_2_UNIT_TESTS.md), with the full output in `docs/test_results/`.

## Evaluation

```bash
python -m src.evaluation --mode groq --runs 2
python -m src.evaluation --mode local --runs 1     # needs a GPU, for example in Colab
python -m src.evaluation --mode groq --only E-09 E-10 E-11
```

Each scenario runs on a fresh database with the service day fixed to Friday 2026-11-06. The runner checks the tool trace, the drafts in the database, and key words in the answer. It grades each run as Pass, Partial, or Fail, and saves the details in `docs/eval_results/`.

Results: [docs/SPRINT_2_EVALUATION.md](docs/SPRINT_2_EVALUATION.md). The Sprint 1 results stay in [docs/SPRINT_1_EVALUATION.md](docs/SPRINT_1_EVALUATION.md).

## Current limitations

- The menu and stock data are synthetic. The product does not prove real allergy safety.
- The inventory API is a mock that we wrote. It is not a real restaurant system.
- Confirming a draft does not reserve stock (PBI-20), and a pickup time in the past is not refused (PBI-15).
- Each MCP call starts a new server process, which takes about one second.
- A session lives as long as the browser tab. There are no accounts, so drafts cannot be found again after a reload.
- Groq's free tier limits output to 1000 tokens per minute. The agent caps each answer at 800 tokens (`GROQ_MAX_TOKENS`) and waits when the limit is reached, so a request can be slow.
- Prompt injection is not tested yet (PBI-19).
- The Streamlit page uses Groq only. Local Qwen runs in the notebook and the evaluation.
