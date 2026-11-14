"""Order-draft management: list, confirm, and cancel. The MCP server exposes these functions.

Confirming never orders or pays: it only changes the status of a draft.
A session can see and change only its own drafts.
"""

from contextlib import closing

from src.db import connect
from src.tools import DRAFT_STATUS, ToolError, _error, _format_eur, _stock_problems, _tool

CONFIRMED = "confirmed"
CANCELLED = "cancelled"


def _draft_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError("invalid_argument", "draft_id must be a positive whole number.")
    return value


def _read_lines(conn, draft_id):
    rows = conn.execute(
        "SELECT o.menu_item_id AS id, m.name, o.quantity, o.unit_price_cents AS price_cents"
        " FROM order_items o JOIN menu_items m ON m.id = o.menu_item_id"
        " WHERE o.draft_order_id = ? ORDER BY o.id",
        (draft_id,),
    )
    return [dict(row) for row in rows]


def _describe(row, lines):
    return {
        "draft_id": row["id"],
        "status": row["status"],
        "service_date": row["service_date"],
        "pickup_time": row["pickup_time"],
        "lines": [
            {
                "name": line["name"],
                "quantity": line["quantity"],
                # The price when the draft was made, not the current menu price.
                "unit_price_eur": _format_eur(line["price_cents"]),
                "unit_price_cents": line["price_cents"],
                "line_total_eur": _format_eur(line["price_cents"] * line["quantity"]),
                "line_total_cents": line["price_cents"] * line["quantity"],
            }
            for line in lines
        ],
        "subtotal_eur": _format_eur(row["subtotal_cents"]),
        "subtotal_cents": row["subtotal_cents"],
        "budget_eur": None if row["budget_cents"] is None else _format_eur(row["budget_cents"]),
    }


def _read_draft(conn, ctx, draft_id):
    """Return (row, lines) of a draft in this session. Another session's draft is not found."""
    row = conn.execute(
        "SELECT * FROM draft_orders WHERE id = ? AND session_id = ?", (draft_id, ctx.session_id)
    ).fetchone()
    if row is None:
        raise ToolError("draft_not_found", f"Draft {draft_id} was not found.")
    return row, _read_lines(conn, draft_id)


def _require_awaiting(row):
    if row["status"] != DRAFT_STATUS:
        raise ToolError(
            "draft_not_awaiting",
            f"Draft {row['id']} is already {row['status']} and cannot be changed.",
            status=row["status"],
        )


def _set_status(ctx, draft_id, status):
    """Change an awaiting draft's status in one transaction, and return the described draft."""
    with closing(connect(ctx.db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row, lines = _read_draft(conn, ctx, draft_id)
        _require_awaiting(row)
        conn.execute("UPDATE draft_orders SET status = ? WHERE id = ?", (status, draft_id))
        return {**_describe(row, lines), "status": status}


@_tool
def list_drafts(ctx):
    """Return this session's drafts, oldest first."""
    with closing(connect(ctx.db_path, read_only=True)) as conn:
        rows = conn.execute(
            "SELECT * FROM draft_orders WHERE session_id = ? ORDER BY id", (ctx.session_id,)
        ).fetchall()
        return {"ok": True, "drafts": [_describe(row, _read_lines(conn, row["id"])) for row in rows]}


@_tool
def cancel_draft(ctx, draft_id):
    """Cancel a draft that is still waiting for confirmation."""
    draft = _set_status(ctx, _draft_id(draft_id), CANCELLED)
    return {"ok": True, "draft": draft, "message": f"Draft {draft['draft_id']} was cancelled."}


@_tool
def confirm_draft(ctx, draft_id):
    """Confirm a draft after checking the stock again. This never orders or pays."""
    draft_id = _draft_id(draft_id)
    with closing(connect(ctx.db_path, read_only=True)) as conn:
        row, lines = _read_draft(conn, ctx, draft_id)
    _require_awaiting(row)
    if row["service_date"] != ctx.service_date.isoformat():
        raise ToolError(
            "draft_expired", f"Draft {draft_id} was made for {row['service_date']}, not for today."
        )
    # Stock can change after the draft was saved. An unreachable API also refuses (fail closed).
    problems = _stock_problems(ctx, lines)
    if problems:
        return _error("confirmation_refused", "The draft was not confirmed.", problems=problems)
    draft = _set_status(ctx, draft_id, CONFIRMED)
    return {
        "ok": True,
        "draft": draft,
        "message": f"Draft {draft_id} is confirmed. No payment was made.",
    }
