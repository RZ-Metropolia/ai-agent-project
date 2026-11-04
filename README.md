# Restaurant Order Agent

A tool-using AI assistant for restaurant pickup orders. A customer writes a request in normal language, for example *"a vegetarian main and a drink for at most 20 euros, pickup at 18:30"*. Qwen chooses tools, and the tools answer from the menu database and the inventory API. The agent saves only an order draft. It never orders or pays.

See [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) and [docs/SPRINT_1_BACKLOG.md](docs/SPRINT_1_BACKLOG.md).

## Project layout

| Path | Contents |
|---|---|
| `src/tools.py` | The six tools. Arguments and results: [docs/CONTRACT.md](docs/CONTRACT.md). |
| `src/agent_tools.py` | LangChain wrappers with Pydantic schemas, and the executor that refuses unknown tools and invalid arguments. |
| `src/agent.py` | The system prompt and the tool-calling loop, with limits and a tool trace. |
| `src/local_model.py` | Local Qwen3.5-4B (4-bit) and the parser for its XML tool calls. |
| `src/cli.py` | Command-line chat. |
| `src/evaluation.py` | The evaluation runner for scenarios E-01 to E-08. |
| `src/db.py`, `data/` | SQLite schema and synthetic seed data. |
| `src/inventory_api.py`, `src/inventory_client.py` | Mock inventory REST API and its client. |
| `notebooks/demo.ipynb` | Colab demo: Groq mode, local mode, and the evaluation. |

## Run it on your computer (Groq mode)

You need Python 3.11 or later and a free Groq API key from https://console.groq.com.

1. Create a virtual environment and install the packages:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`, and set `GROQ_API_KEY` in `.env`.
3. Create the database:

   ```bash
   python -m src.db
   ```

4. Start the chat. It starts the mock inventory API by itself.

   ```bash
   python -m src.cli --trace
   ```

   `--trace` shows each tool call and its result. Type `quit` to stop.

## Run it in Colab (Groq and local mode)

1. Open `notebooks/demo.ipynb` in Colab.
2. Add `GROQ_API_KEY` as a Colab secret (the key icon on the left).
3. For local mode, select **Runtime → Change runtime type → T4 GPU**.
4. Run the cells from the top.

## Tests

```bash
python -m unittest discover tests
```

The tests need no API key and no GPU. A scripted fake model replaces Qwen.

## Evaluation

```bash
python -m src.evaluation --mode groq --runs 2
python -m src.evaluation --mode local --runs 1     # needs a GPU, for example in Colab
```

Each scenario runs on a fresh database with the service day fixed to Friday 2026-11-06. The runner checks the tool trace, the saved drafts, and key words in the answer. It grades each run as Pass, Partial, or Fail, and saves the details in `docs/eval_results/`.
