"""Logic behind the Streamlit page. It is kept apart from the page so that it can be unit tested."""

import json
import os
import uuid
from dataclasses import replace

from dotenv import load_dotenv

from src import mcp_client
from src.agent import DEFAULT_GROQ_MODEL, build_model, run_agent
from src.agent_tools import make_tools
from src.config import load_context
from src.inventory_client import InventoryClient

EXAMPLE_REQUESTS = (
    "Prepare a vegetarian pickup order for one person at 18:30: one main course and one drink,"
    " with a total of at most 20 euros.",
    "Which main courses are both vegan and gluten-free today?",
    "Which drafts do I have?",
)
STATUS_LABELS = {
    "awaiting_customer_confirmation": "Waiting for your confirmation",
    "confirmed": "Confirmed",
    "cancelled": "Cancelled",
}
PATH_LABELS = {"mcp": "MCP server", "direct": "Python tool"}
RESULT_PREVIEW_CHARS = 600


def new_session_id():
    return uuid.uuid4().hex


def build_context(inventory_url, session_id):
    """The tool context for one browser session, using the inventory API that the page started."""
    ctx = load_context()
    return replace(
        ctx,
        inventory=InventoryClient(inventory_url, timeout=ctx.inventory.timeout),
        session_id=session_id,
    )


def model_name():
    load_dotenv()
    return os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL


def load_model():
    """Return (model, problem). Without a key there is no model, and `problem` says why."""
    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        return None, "GROQ_API_KEY is not set. Copy .env.example to .env and add your Groq key."
    return build_model("groq"), None


def ask(model, ctx, request, history):
    """Run one customer request. Return the result and the history for the next request."""
    result = run_agent(model, ctx, make_tools(ctx), request, history)
    return result, result.messages[1:]  # Without the system prompt.


def trace_rows(trace):
    """The tool calls of one answer, prepared for display."""
    rows = []
    for step in trace:
        result = step["result"]
        text = json.dumps(result, ensure_ascii=False)
        rows.append(
            {
                "tool": step["tool"],
                "path": PATH_LABELS[step["path"]],
                "arguments": json.dumps(step["args"], ensure_ascii=False),
                "outcome": "ok" if result.get("ok") else result["error"]["code"],
                "result": text[:RESULT_PREVIEW_CHARS] + ("…" if len(text) > RESULT_PREVIEW_CHARS else ""),
            }
        )
    return rows


def failure_message(result):
    """One readable sentence for a refused call, with every listed problem."""
    problems = " ".join(problem["message"] for problem in result.get("problems", []))
    return f"{result['error']['message']} {problems}".strip()


def load_cart(ctx):
    """Return (drafts, problem) from the MCP server. The newest draft comes first."""
    result = mcp_client.list_drafts(ctx)
    if not result["ok"]:
        return [], failure_message(result)
    drafts = [
        {
            **draft,
            "status_label": STATUS_LABELS[draft["status"]],
            "can_change": draft["status"] == "awaiting_customer_confirmation",
        }
        for draft in reversed(result["drafts"])
    ]
    return drafts, None


def change_draft(ctx, action, draft_id):
    """Confirm or cancel a draft through the MCP server. Return (succeeded, message)."""
    call = {"confirm": mcp_client.confirm_draft, "cancel": mcp_client.cancel_draft}[action]
    result = call(ctx, draft_id)
    if result["ok"]:
        return True, result["message"]
    return False, failure_message(result)
