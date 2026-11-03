"""Local Qwen3.5-4B (4-bit) for Colab, with a parser for its XML tool calls.

Qwen3.5 writes tool calls in this format (see the model's chat_template.jinja):

    <tool_call>
    <function=calculate_total>
    <parameter=items>
    [{"name": "Grilled Salmon", "quantity": 2}]
    </parameter>
    <parameter=budget_eur>
    30
    </parameter>
    </function>
    </tool_call>
"""

import json
import re
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.agent import strip_thinking
from src.agent_tools import make_tools

LOCAL_MODEL_ID = "Qwen/Qwen3.5-4B"

TOOL_CALL = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.S)
FUNCTION = re.compile(r"<function=([^>\s]+)>(.*?)(?:</function>|$)", re.S)
PARAMETER = re.compile(r"<parameter=([^>\s]+)>\n?(.*?)\n?</parameter>", re.S)


def _value(raw):
    """Lists, objects, and numbers are JSON. Text is written without quotes."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()


def parse_tool_calls(text):
    """Split the model output into the answer text and a list of LangChain tool calls."""
    text = strip_thinking(text)
    calls = []
    for block in TOOL_CALL.findall(text):
        function = FUNCTION.search(block)
        # A broken call goes to the executor as an unknown tool, so the model sees an error.
        name = function[1] if function else "malformed_tool_call"
        args = {key: _value(raw) for key, raw in PARAMETER.findall(function[2])} if function else {}
        calls.append({"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"})
    return TOOL_CALL.sub("", text).strip(), calls


def to_chat_messages(messages):
    """Convert LangChain messages to the dictionaries that the chat template expects."""
    chat = []
    for message in messages:
        if isinstance(message, SystemMessage):
            chat.append({"role": "system", "content": message.content})
        elif isinstance(message, HumanMessage):
            chat.append({"role": "user", "content": message.content})
        elif isinstance(message, AIMessage):
            chat.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {"type": "function", "function": {"name": c["name"], "arguments": c["args"]}}
                        for c in message.tool_calls
                    ],
                }
            )
        elif isinstance(message, ToolMessage):
            chat.append({"role": "tool", "content": message.content})
    return chat


class LocalQwen:
    """Qwen3.5-4B in 4-bit (NF4) on a Colab GPU. Same interface as the Groq model."""

    def __init__(self, model_id=LOCAL_MODEL_ID, max_new_tokens=1024):
        import torch
        from transformers import AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig

        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        # Qwen3.5 is a vision-language model; we use only its text part.
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            device_map="auto",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,  # The Colab T4 GPU has no bfloat16.
            ),
        )
        self.max_new_tokens = max_new_tokens
        self.tools = [convert_to_openai_tool(tool) for tool in make_tools(None).values()]

    def invoke(self, messages):
        inputs = self.tokenizer.apply_chat_template(
            to_chat_messages(messages),
            tools=self.tools,
            add_generation_prompt=True,
            enable_thinking=False,  # Faster, and the evaluation uses the same setting for every run.
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        new_tokens = output[0][inputs["input_ids"].shape[1] :]
        content, calls = parse_tool_calls(self.tokenizer.decode(new_tokens, skip_special_tokens=True))
        return AIMessage(content=content, tool_calls=calls)
