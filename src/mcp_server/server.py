"""MCP server "restaurant-order-service": list, cancel, and confirm order drafts.

The application starts this server by itself, as a child process that talks over stdio.
The server reads its settings from the environment (see load_context in src/config.py).
Each tool takes the customer's session ID, because the server process has no session of its own.
"""

import re
from dataclasses import replace

from mcp.server.fastmcp import FastMCP

from src import orders
from src.config import load_context

mcp = FastMCP("restaurant-order-service", log_level="WARNING")

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _run(function, session_id, *args):
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        return {
            "ok": False,
            "error": {"code": "invalid_argument", "message": "session_id is missing or invalid."},
        }
    return function(replace(load_context(), session_id=session_id), *args)


@mcp.tool()
def list_drafts(session_id: str) -> dict:
    """List the order drafts of one customer session, with their lines, totals, and status."""
    return _run(orders.list_drafts, session_id)


@mcp.tool()
def cancel_draft(session_id: str, draft_id: int) -> dict:
    """Cancel a draft that is waiting for confirmation."""
    return _run(orders.cancel_draft, session_id, draft_id)


@mcp.tool()
def confirm_draft(session_id: str, draft_id: int) -> dict:
    """Confirm a draft after checking live stock again. This never orders or pays."""
    return _run(orders.confirm_draft, session_id, draft_id)
