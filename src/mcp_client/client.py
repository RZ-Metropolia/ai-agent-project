"""MCP client: starts the order-service MCP server over stdio and calls its tools.

Each call opens a short connection: start the server process, initialize, call, and close.
That is slower than one long connection, but it needs no shared state, so it works the same
in Streamlit, the CLI, a notebook, and the tests.

Nothing here raises to the caller. A failure becomes {"ok": False, "error": {...}}.
"""

import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SERVER_COMMAND = (sys.executable, "-m", "src.mcp_server")
CALL_TIMEOUT_SECONDS = 30.0


def _error(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def server_parameters(ctx):
    """How to start the server so that it uses the same database, API, and service day as `ctx`."""
    command = ctx.order_service_command or DEFAULT_SERVER_COMMAND
    env = {
        "RESTAURANT_DB_PATH": str(ctx.db_path),
        "SERVICE_DATE": ctx.service_date.isoformat(),
        "RESTAURANT_TIMEZONE": ctx.timezone.key,
    }
    base_url = getattr(ctx.inventory, "base_url", None)
    if base_url:
        env["INVENTORY_API_URL"] = base_url
        env["INVENTORY_TIMEOUT_SECONDS"] = str(ctx.inventory.timeout)
    return StdioServerParameters(
        command=command[0], args=list(command[1:]), env=env, cwd=PROJECT_ROOT
    )


async def _with_session(parameters, action):
    # The server's stderr is dropped: sys.stderr in a notebook cannot be given to a process.
    with open(os.devnull, "w") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await action(session)


def _run(parameters, action):
    """Run `action(session)` and wait for it. A thread keeps this safe inside a running event loop."""

    async def limited():
        return await asyncio.wait_for(_with_session(parameters, action), CALL_TIMEOUT_SECONDS)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, limited()).result()


def parse_result(result):
    """Turn an MCP tool result into the dictionary format of our tools."""
    text = "".join(block.text for block in result.content if getattr(block, "type", "") == "text")
    if result.isError:
        return _error("mcp_tool_error", f"The order service refused the call: {text}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or "ok" not in data:
        return _error("mcp_bad_response", "The order service returned an unexpected result.")
    return data


def call_tool(ctx, name, arguments):
    """Call one tool on the MCP server and return its result as a dictionary."""
    try:
        result = _run(server_parameters(ctx), lambda session: session.call_tool(name, arguments))
    except Exception:  # The server did not start, crashed, or did not answer in time.
        return _error("mcp_unavailable", "The order service is not available right now.")
    return parse_result(result)


def list_tool_names(ctx):
    """Return the names of the tools that the MCP server offers."""

    async def action(session):
        return [tool.name for tool in (await session.list_tools()).tools]

    return _run(server_parameters(ctx), action)


# The session ID comes from `ctx`, never from the model.


def list_drafts(ctx):
    return call_tool(ctx, "list_drafts", {"session_id": ctx.session_id})


def cancel_draft(ctx, draft_id):
    return call_tool(ctx, "cancel_draft", {"session_id": ctx.session_id, "draft_id": draft_id})


def confirm_draft(ctx, draft_id):
    return call_tool(ctx, "confirm_draft", {"session_id": ctx.session_id, "draft_id": draft_id})
