"""Command-line chat with the restaurant order agent.

Run from the project root:
    python -m src.cli                 # Qwen on Groq
    python -m src.cli --trace         # also show the tool calls
    python -m src.cli --mode local    # local Qwen3.5-4B (needs a GPU)

The chat starts its own mock inventory API in the background. The MCP client starts the
MCP server when a draft is listed, cancelled, or confirmed.
"""

import argparse
import re
from dataclasses import replace

from src import app_logic
from src.agent import build_model, print_trace, run_agent
from src.agent_tools import make_tools
from src.config import load_context
from src.db import ensure_db
from src.inventory_api import BackgroundServer
from src.inventory_client import InventoryClient


def main():
    parser = argparse.ArgumentParser(description="Chat with the restaurant order agent.")
    parser.add_argument("--mode", choices=["groq", "local"], default="groq")
    parser.add_argument("--trace", action="store_true", help="show the tool calls")
    args = parser.parse_args()

    context = load_context()
    if ensure_db(context.db_path):
        print(f"Created {context.db_path}")
    model = build_model(args.mode)

    with BackgroundServer() as server:
        ctx = replace(
            context, inventory=InventoryClient(server.url), session_id=app_logic.new_session_id()
        )
        tool_map = make_tools(ctx)
        print(f"Service day: {ctx.service_date:%A %Y-%m-%d}.")
        print("Type 'confirm 1' to confirm draft 1 yourself, or 'quit' to stop.")
        history = []
        while True:
            try:
                request = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if request.lower() in {"quit", "exit"}:
                break
            if not request:
                continue
            # Confirming is the customer's own action, so it does not go through the model.
            confirm = re.fullmatch(r"confirm\s+#?(\d+)", request, flags=re.I)
            if confirm:
                print(app_logic.change_draft(ctx, "confirm", int(confirm[1]))[1])
                continue
            result = run_agent(model, ctx, tool_map, request, history)
            history = result.messages[1:]  # Without the system prompt.
            if args.trace:
                print_trace(result)
            print(f"\nAgent: {result.answer}")


if __name__ == "__main__":
    main()
