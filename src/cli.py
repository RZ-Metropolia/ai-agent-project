"""Command-line chat with the restaurant order agent.

Run from the project root:
    python -m src.cli                 # Qwen on Groq
    python -m src.cli --trace         # also show the tool calls
    python -m src.cli --mode local    # local Qwen3.5-4B (needs a GPU)

The chat starts its own mock inventory API in the background.
"""

import argparse
from dataclasses import replace

from src.agent import build_model, print_trace, run_agent
from src.agent_tools import make_tools
from src.config import load_context
from src.db import DB_PATH, init_db
from src.inventory_api import BackgroundServer
from src.inventory_client import InventoryClient


def main():
    parser = argparse.ArgumentParser(description="Chat with the restaurant order agent.")
    parser.add_argument("--mode", choices=["groq", "local"], default="groq")
    parser.add_argument("--trace", action="store_true", help="show the tool calls")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Created {init_db()}")
    model = build_model(args.mode)

    with BackgroundServer() as server:
        ctx = replace(load_context(), inventory=InventoryClient(server.url))
        tool_map = make_tools(ctx)
        print(f"Service day: {ctx.service_date:%A %Y-%m-%d}. Type 'quit' to stop.")
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
            result = run_agent(model, ctx, tool_map, request, history)
            history = result.messages[1:]  # Without the system prompt.
            if args.trace:
                print_trace(result)
            print(f"\nAgent: {result.answer}")


if __name__ == "__main__":
    main()
