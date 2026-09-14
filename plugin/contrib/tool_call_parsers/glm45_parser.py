"""
GLM 4.5 (GLM-4-MoE) tool call parser.

Format uses custom arg_key/arg_value tags rather than standard JSON:
    <tool_call>function_name
    <arg_key>param1</arg_key><arg_value>value1</arg_value>
    <arg_key>param2</arg_key><arg_value>value2</arg_value>
    </tool_call>

Argument values are kept as raw strings (vLLM Glm47MoeModelToolParser).
_deserialize_value remains for callers that still want literal conversion.

Based on VLLM's Glm47MoeModelToolParser.extract_tool_calls()
"""

import json
import re
import uuid
from typing import Any, Dict, List

from plugin.framework.errors import safe_python_literal_eval
from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser


def _deserialize_value(value: str) -> Any:
    """
    Try to deserialize a string value to its native Python type.
    Attempts json.loads, then safe_python_literal_eval, then returns raw string.
    """
    # Try JSON (via safe_json_loads) and common Python literals safely
    return safe_python_literal_eval(value, default=value)


@register_parser("glm45")
class Glm45ToolCallParser(ToolCallParser):
    """
    Parser for GLM 4.5 (GLM-4-MoE) tool calls.

    Uses <tool_call>...</tool_call> tags with <arg_key>/<arg_value> pairs
    instead of standard JSON arguments.
    """

    # vLLM Glm47MoeModelToolParser: no required newline, zero-arg legal
    FUNC_CALL_REGEX = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
    FUNC_ARG_REGEX = re.compile(
        r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.DOTALL
    )

    START_TOKEN = "<tool_call>"

    def parse(self, text: str) -> ParseResult:
        if self.START_TOKEN not in text:
            return text, None

        try:
            matched_calls = self.FUNC_CALL_REGEX.findall(text)
            if not matched_calls:
                return text, None

            tool_calls: List[ChatCompletionMessageToolCall] = []

            for match in matched_calls:
                first_arg = match.find("<arg_key>")
                if first_arg < 0:
                    func_name = match.strip()
                    arg_dict: Dict[str, Any] = {}
                else:
                    func_name = match[:first_arg].strip()
                    pairs = self.FUNC_ARG_REGEX.findall(match[first_arg:])
                    # Keys stripped; values kept raw (vLLM no longer literal_evals)
                    arg_dict = {key.strip(): value for key, value in pairs}

                if not func_name:
                    continue

                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=Function(
                            name=func_name,
                            arguments=json.dumps(arg_dict, ensure_ascii=False),
                        ),
                    )
                )

            if not tool_calls:
                return text, None

            content = text[: text.find(self.START_TOKEN)].strip()
            return content if content else None, tool_calls

        except Exception:
            return text, None
