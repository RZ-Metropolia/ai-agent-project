"""Streamlit page for the restaurant order agent.

Run from the project root:
    streamlit run app.py

The page starts the mock inventory API by itself. The MCP server is started by the MCP client
when a draft is listed, cancelled, or confirmed. This file only draws the page: the logic is
in src/app_logic.py.
"""

import streamlit as st

from src import app_logic
from src.db import ensure_db
from src.inventory_api import BackgroundServer
from src.inventory_client import set_inventory_mode

st.set_page_config(page_title="Restaurant Order Agent", page_icon="🍽️", layout="wide")


@st.cache_resource
def inventory_api():
    """One mock inventory API for the whole Streamlit process."""
    return BackgroundServer().start()


def init_state():
    state = st.session_state
    state.setdefault("session_id", app_logic.new_session_id())
    state.setdefault("history", [])  # The conversation for the model.
    state.setdefault("turns", [])  # The conversation for the page.
    state.setdefault("cart", None)  # (drafts, problem), or None when it must be loaded again.
    state.setdefault("notice", None)  # (succeeded, message) of the last button action.
    if "model" not in state:
        state.model, state.model_problem = app_logic.load_model()


def switch_outage():
    set_inventory_mode(inventory_api().url, "outage" if st.session_state.outage else "normal")


def change_draft(action, draft_id):
    st.session_state.notice = app_logic.change_draft(ctx, action, draft_id)
    st.session_state.cart = None


def queue_request(request):
    st.session_state.pending_request = request


def draw_draft(draft):
    with st.container(border=True):
        st.markdown(f"**Draft #{draft['draft_id']}** · pickup {draft['pickup_time']}")
        st.caption(draft["status_label"])
        for line in draft["lines"]:
            st.text(f"{line['quantity']} × {line['name']}  {line['line_total_eur']} €")
        st.markdown(f"**Total {draft['subtotal_eur']} €**")
        if draft["can_change"]:
            left, right = st.columns(2)
            left.button(
                "Confirm", key=f"confirm_{draft['draft_id']}", type="primary",
                on_click=change_draft, args=("confirm", draft["draft_id"]), use_container_width=True,
            )
            right.button(
                "Cancel", key=f"cancel_{draft['draft_id']}",
                on_click=change_draft, args=("cancel", draft["draft_id"]), use_container_width=True,
            )


def draw_sidebar():
    with st.sidebar:
        st.header("Today")
        st.markdown(
            f"Service day: **{ctx.service_date:%A %Y-%m-%d}**  \n"
            f"Pickup hours: **{ctx.pickup_open:%H:%M}–{ctx.pickup_close:%H:%M}**  \n"
            f"Model: `{app_logic.model_name()}` on Groq"
        )

        st.header("Your drafts")
        if st.session_state.notice:
            succeeded, message = st.session_state.notice
            (st.success if succeeded else st.error)(message)
        if st.session_state.cart is None:
            st.session_state.cart = app_logic.load_cart(ctx)
        drafts, problem = st.session_state.cart
        if problem:
            st.error(problem)
        elif not drafts:
            st.caption("No drafts yet. Ask the assistant to prepare an order.")
        for draft in drafts:
            draw_draft(draft)
        st.caption("A draft is not an order. Confirming does not pay.")

        st.header("Demo")
        st.toggle(
            "Simulate an inventory API outage", key="outage", on_change=switch_outage,
            help="The mock inventory API then returns HTTP 503 for every session.",
        )


def draw_turn(turn):
    with st.chat_message("user"):
        st.markdown(turn["request"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        if turn["error"]:
            st.caption(f"Model error: {turn['error'][:300]}")
        if turn["trace"]:
            with st.expander(f"Tool calls ({len(turn['trace'])})"):
                for number, row in enumerate(turn["trace"], 1):
                    st.markdown(f"**{number}. `{row['tool']}`** · {row['path']} · {row['outcome']}")
                    st.code(f"arguments: {row['arguments']}\nresult: {row['result']}", language="json")


init_state()
inventory = inventory_api()
ctx = app_logic.build_context(inventory.url, st.session_state.session_id)
ensure_db(ctx.db_path)

draw_sidebar()

st.title("Restaurant Order Agent")
st.caption(
    "Ask for dishes that match your diet, allergies, and budget. Every price, allergen, and stock"
    " value comes from the restaurant's tools. The assistant prepares drafts and never orders or pays."
)

if st.session_state.model_problem:
    st.error(st.session_state.model_problem)
    st.stop()

for turn in st.session_state.turns:
    draw_turn(turn)

request = st.chat_input("Ask about the menu or an order") or st.session_state.pop(
    "pending_request", None
)

if not st.session_state.turns and not request:
    st.markdown("**Try one of these:**")
    for number, example in enumerate(app_logic.EXAMPLE_REQUESTS):
        st.button(example, key=f"example_{number}", on_click=queue_request, args=(example,))

if request:
    with st.chat_message("user"):
        st.markdown(request)
    with st.chat_message("assistant"), st.spinner("Checking the menu and order tools…"):
        result, st.session_state.history = app_logic.ask(
            st.session_state.model, ctx, request, st.session_state.history
        )
    st.session_state.turns.append(
        {
            "request": request,
            "answer": result.answer,
            "error": result.error,
            "trace": app_logic.trace_rows(result.trace),
        }
    )
    st.session_state.cart = None  # The request may have saved or cancelled a draft.
    st.session_state.notice = None
    st.rerun()
