"""
Qwen3-Coder tool call parser.

Format uses XML-style nested tags:
    <tool_call>
    <function=function_name>
    <parameter=param_name>value</parameter>
    <parameter=param_name2>value2</parameter>
    </function>
    </tool_call>

Parameters are extracted from <parameter=name>value</parameter> tags and
type-converted using the schema if available, otherwise treated as strings.

Based on VLLM's Qwen3CoderToolParser.extract_tool_calls()
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from plugin.framework.errors import safe_python_literal_eval
from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser


def _try_convert_value(value: str) -> Any:
    """
    Try to convert a parameter value string to a native Python type.
    Handles null, numbers, booleans, JSON objects/arrays, and falls back to string.
    """
    stripped = value.strip()

    # Handle null
    if stripped.lower() == "null":
        return None

    # Try JSON and common Python literals safely
    return safe_python_literal_eval(stripped, default=stripped)


@register_parser("qwen3_coder")
@register_parser("qwen3_xml")
@register_parser("mimo")
class Qwen3CoderToolCallParser(ToolCallParser):
    """
    Parser for Qwen3-Coder XML-format tool calls.

    Uses nested XML tags: <tool_call><function=name><parameter=key>val</parameter></function></tool_call>
    qwen3_xml and mimo are vLLM aliases for the same tags.
    """

    START_TOKEN = "<tool_call>"
    FUNCTION_PREFIX = "<function="

    # Whitespace-tolerant tags (vLLM qwen3.py _PARAM_RE)
    TOOL_CALL_REGEX = re.compile(
        r"<\s*tool_call\s*>(.*?)</\s*tool_call\s*>|<\s*tool_call\s*>(.*?)$",
        re.DOTALL,
    )

    FUNCTION_REGEX = re.compile(
        r"<\s*function\s*=\s*(.*?)</\s*function\s*>|<\s*function\s*=\s*(.*)$",
        re.DOTALL,
    )

    PARAMETER_REGEX = re.compile(
        r"<\s*parameter\s*=\s*(.*?)(?:<\s*/\s*parameter\s*>|(?=<\s*parameter\s*=)|(?=<\s*/\s*function)|$)",
        re.DOTALL,
    )

    def _parse_function_call(self, function_str: str) -> Optional[ChatCompletionMessageToolCall]:
        """Parse a single <function=name>...</function> block into a ToolCall."""
        try:
            # Extract function name: everything before the first '>'
            gt_idx = function_str.index(">")
            func_name = function_str[:gt_idx].strip()
            params_str = function_str[gt_idx + 1:]

            # Extract parameters
            param_dict: Dict[str, Any] = {}
            for match_text in self.PARAMETER_REGEX.findall(params_str):
                if ">" not in match_text:
                    continue
                eq_idx = match_text.index(">")
                param_name = match_text[:eq_idx].strip()
                param_value = match_text[eq_idx + 1:]

                # Clean up whitespace
                if param_value.startswith("\n"):
                    param_value = param_value[1:]
                if param_value.endswith("\n"):
                    param_value = param_value[:-1]

                param_dict[param_name] = _try_convert_value(param_value)

            return ChatCompletionMessageToolCall(
                id=f"call_{uuid.uuid4().hex[:24]}",
                type="function",
                function=Function(
                    name=func_name,
                    arguments=json.dumps(param_dict, ensure_ascii=False),
                ),
            )
        except (ValueError, IndexError):
            return None

    def parse(self, text: str) -> ParseResult:
        if "function=" not in text:
            return text, None

        try:
            # Find all tool_call blocks
            tc_matches = self.TOOL_CALL_REGEX.findall(text)
            raw_blocks = [m[0] if m[0] else m[1] for m in tc_matches]

            # Fallback: if no tool_call tags, try the whole text
            if not raw_blocks:
                raw_blocks = [text]

            # Find function blocks within each tool_call
            function_strs: List[str] = []
            for block in raw_blocks:
                func_matches = self.FUNCTION_REGEX.findall(block)
                function_strs.extend(m[0] if m[0] else m[1] for m in func_matches)

            if not function_strs:
                return text, None

            # Parse each function call
            tool_calls: List[ChatCompletionMessageToolCall] = []
            for func_str in function_strs:
                tc = self._parse_function_call(func_str)
                if tc is not None:
                    tool_calls.append(tc)

            if not tool_calls:
                return text, None

            # Content before tool calls
            first_tc = text.find(self.START_TOKEN)
            if first_tc < 0:
                first_tc = text.find(self.FUNCTION_PREFIX)
            content = text[:first_tc].strip() if first_tc > 0 else None

            return content, tool_calls

        except Exception:
            return text, None
