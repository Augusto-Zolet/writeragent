"""
Llama 4 pythonic tool call parser.

Strips <|python_start|> / <|python_end|> then ast-parses a list of calls:

    [get_weather(city="Paris", unit="celsius")]

Based on VLLM's Llama4PythonicToolParser.extract_tool_calls()
"""

import ast
import json
import re
import uuid
from typing import Any, List

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser

_JSON_NAME_LITERALS = {
    "null": None,
    "true": True,
    "false": False,
}

TOOL_CALL_REGEX = re.compile(
    r"\[([a-zA-Z]+\w*\(([a-zA-Z]+\w*=.*,\s*)*([a-zA-Z]+\w*=.*\s)?\),\s*)*"
    r"([a-zA-Z]+\w*\(([a-zA-Z]+\w*=.*,\s*)*([a-zA-Z]+\w*=.*\s*)?\)\s*)+\]",
    re.DOTALL,
)


def _ast_callable_dotted_name(node: ast.expr) -> str:
    parts: List[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        raise ValueError("Invalid tool call name")
    parts.append(current.id)
    return ".".join(reversed(parts))


def _get_parameter_value(val: ast.expr) -> Any:
    if isinstance(val, ast.Constant):
        if val.value is None or isinstance(val.value, (str, int, float, bool)):
            return val.value
        raise ValueError("Tool call arguments must be JSON values")
    if isinstance(val, ast.Dict):
        if not all(isinstance(k, ast.Constant) for k in val.keys):
            raise ValueError("Dict tool call arguments must have literal keys")
        return {k.value: _get_parameter_value(v) for k, v in zip(val.keys, val.values)}  # type: ignore[union-attr]
    if isinstance(val, ast.List):
        return [_get_parameter_value(v) for v in val.elts]
    if isinstance(val, ast.Tuple):
        return [_get_parameter_value(v) for v in val.elts]
    if isinstance(val, ast.Set):
        return [_get_parameter_value(v) for v in val.elts]
    if isinstance(val, ast.Name) and val.id in _JSON_NAME_LITERALS:
        return _JSON_NAME_LITERALS[val.id]
    if isinstance(val, ast.UnaryOp) and isinstance(val.op, (ast.USub, ast.UAdd)):
        operand = _get_parameter_value(val.operand)
        if isinstance(operand, (int, float)) and not isinstance(operand, bool):
            return -operand if isinstance(val.op, ast.USub) else operand
        raise ValueError("Tool call arguments must be literals")
    raise ValueError("Tool call arguments must be literals")


def _handle_single_tool(call: ast.Call) -> ChatCompletionMessageToolCall:
    if not isinstance(call.func, (ast.Name, ast.Attribute)):
        raise ValueError("Invalid tool call name")
    function_name = _ast_callable_dotted_name(call.func)
    arguments = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        arguments[keyword.arg] = _get_parameter_value(keyword.value)
    return ChatCompletionMessageToolCall(
        id=f"call_{uuid.uuid4().hex[:8]}",
        type="function",
        function=Function(
            name=function_name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )


@register_parser("llama4_pythonic")
class Llama4PythonicToolCallParser(ToolCallParser):
    """Parser for Llama 4 pythonic [fn(a=1)] tool dumps."""

    def parse(self, text: str) -> ParseResult:
        model_output = text
        if model_output.startswith("<|python_start|>"):
            model_output = model_output[len("<|python_start|>") :]
            model_output = model_output.replace("<|python_end|>", "")

        stripped = model_output.strip()
        if not TOOL_CALL_REGEX.match(stripped):
            return text, None

        try:
            module = ast.parse(stripped)
            parsed = getattr(module.body[0], "value", None)
            if not isinstance(parsed, ast.List) or not all(
                isinstance(e, ast.Call) for e in parsed.elts
            ):
                return text, None
            tool_calls = [_handle_single_tool(e) for e in parsed.elts]  # type: ignore[arg-type]
            if not tool_calls:
                return text, None
            return None, tool_calls
        except Exception:
            return text, None
