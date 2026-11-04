"""The system prompt and the tool-calling loop. The same loop runs with Groq and with local Qwen."""

import json
import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.agent_tools import execute_tool, make_tools

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
MAX_ROUNDS = 8  # Model calls per request.
MAX_TOOL_CALLS = 12  # Tool calls per request.
MODEL_RETRIES = 2  # Extra tries when Groq refuses a garbled tool call.

SYSTEM_PROMPT = """You are the pickup-order assistant of a restaurant.
You help customers find dishes and prepare an order draft for pickup today.

Rules:
1. Use only facts from tool results: dish names, prices, ingredients, allergens, and stock. Never guess.
2. For allergy questions, use get_ingredients or filter_dietary_options. Never judge from the dish name.
3. Never calculate prices yourself. Use calculate_total or draft_order, and copy the *_eur values.
4. Use the exact dish names that the tools return.
5. To prepare an order: find dishes that match the request, check stock with check_availability,
   then call draft_order. Give draft_order the customer's dietary labels, allergens, and budget.
6. If a tool refuses or fails, tell the customer the reason in plain words. If stock cannot be
   checked, say so. Never invent a stock value. Offer alternatives only from tool results.
7. A draft is not an order. Tell the customer that they must confirm the draft.
   You cannot place orders or take payments.
8. Pickup hours are {pickup_open}-{pickup_close}.

Answer briefly and in the customer's language."""


def system_prompt(ctx):
    return SYSTEM_PROMPT.format(
        pickup_open=f"{ctx.pickup_open:%H:%M}", pickup_close=f"{ctx.pickup_close:%H:%M}"
    )


@dataclass
class AgentResult:
    answer: str
    trace: list = field(default_factory=list)  # One entry per tool call: tool, args, result.
    messages: list = field(default_factory=list)  # The full conversation, for the next turn.
    stop_reason: str = "answer"  # answer, round_limit, tool_limit, or model_error.
    retries: int = 0  # Model calls that were tried again.


def strip_thinking(text):
    """Remove Qwen's <think>...</think> block from an answer."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def is_tool_call_error(exc):
    """Groq checks each tool call. A misspelled tool name gives HTTP 400 'tool_use_failed'."""
    return "tool_use_failed" in str(exc)


def run_agent(model, ctx, tool_map, request, history=None):
    """Answer one customer request. `history` is the earlier conversation, without the system prompt."""
    messages = [SystemMessage(system_prompt(ctx)), *(history or []), HumanMessage(request)]
    trace = []
    retries = 0

    def stop(answer, reason):
        return AgentResult(answer, trace, messages, reason, retries)

    for _ in range(MAX_ROUNDS):
        for attempt in range(MODEL_RETRIES + 1):
            try:
                reply = model.invoke(messages)
                break
            except Exception as exc:  # A model or network error must not crash the chat.
                # Groq output varies between calls, so a garbled tool call is worth another try.
                if attempt < MODEL_RETRIES and is_tool_call_error(exc):
                    retries += 1
                    continue
                return stop(f"Sorry, the language model failed: {exc}", "model_error")
        messages.append(reply)
        if not reply.tool_calls:
            return stop(strip_thinking(reply.content), "answer")

        if len(trace) + len(reply.tool_calls) > MAX_TOOL_CALLS:
            messages.pop()  # Keep the history valid: every tool call needs a tool result.
            return stop("Sorry, this request needed too many steps. Please ask again.", "tool_limit")
        for call in reply.tool_calls:
            result = execute_tool(tool_map, call["name"], call["args"])
            trace.append({"tool": call["name"], "args": call["args"], "result": result})
            messages.append(ToolMessage(json.dumps(result), tool_call_id=call["id"]))

    return stop("Sorry, I could not finish this request. Please ask again.", "round_limit")


def groq_model(model_name=None):
    """Qwen on Groq. Needs GROQ_API_KEY in the environment or in .env."""
    from langchain_groq import ChatGroq

    load_dotenv()
    llm = ChatGroq(
        model=model_name or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL, temperature=0
    )
    return llm.bind_tools(list(make_tools(None).values()))


def build_model(mode):
    """Return a model for 'groq' or 'local'. Both have invoke(messages) -> AIMessage."""
    if mode == "groq":
        return groq_model()
    if mode == "local":
        from src.local_model import LocalQwen

        return LocalQwen()
    raise ValueError(f"Unknown mode: {mode}")


def print_trace(result):
    for number, step in enumerate(result.trace, 1):
        print(f"  [{number}] {step['tool']}({json.dumps(step['args'], ensure_ascii=False)})")
        print(f"      -> {json.dumps(step['result'], ensure_ascii=False)[:300]}")
