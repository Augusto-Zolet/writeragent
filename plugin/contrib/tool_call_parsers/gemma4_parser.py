"""
Gemma 4 tool call parser.

    <|tool_call>call:func_name{key:<|"|>value<|"|>,num:42}<tool_call|>

Based on VLLM's _parse_gemma4_args (non-streaming only).
"""

import json
import re
import uuid
from typing import Any, Dict, List

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser

TOOL_CALL_START = "<|tool_call>"
TOOL_CALL_END = "<tool_call|>"
STRING_DELIM = '<|"|>'
_DELIM_LEN = len(STRING_DELIM)


def _parse_gemma4_args(args_str: str) -> Dict[str, Any]:
    """Parse Gemma4 key:value dumps (strings, nested objects, arrays, bare tokens)."""
    if not args_str or not args_str.strip():
        return {}

    result: Dict[str, Any] = {}
    i = 0
    n = len(args_str)

    while i < n:
        while i < n and args_str[i] in (" ", ",", "\n", "\t"):
            i += 1
        if i >= n:
            break

        key_start = i
        while i < n and args_str[i] != ":":
            i += 1
        if i >= n:
            break
        key = args_str[key_start:i].strip()
        if key.startswith(STRING_DELIM) and key.endswith(STRING_DELIM):
            key = key[_DELIM_LEN:-_DELIM_LEN]
        i += 1

        if i >= n:
            result[key] = ""
            break

        while i < n and args_str[i] in (" ", "\n", "\t"):
            i += 1
        if i >= n:
            result[key] = ""
            break

        if args_str[i : i + _DELIM_LEN] == STRING_DELIM:
            i += _DELIM_LEN
            end_pos = args_str.find(STRING_DELIM, i)
            if end_pos == -1:
                result[key] = args_str[i:]
                break
            result[key] = args_str[i:end_pos]
            i = end_pos + _DELIM_LEN

        elif args_str[i] == "{":
            depth = 1
            obj_start = i + 1
            i += 1
            while i < n and depth > 0:
                if args_str[i : i + _DELIM_LEN] == STRING_DELIM:
                    i += _DELIM_LEN
                    next_delim = args_str.find(STRING_DELIM, i)
                    i = n if next_delim == -1 else next_delim + _DELIM_LEN
                    continue
                if args_str[i] == "{":
                    depth += 1
                elif args_str[i] == "}":
                    depth -= 1
                i += 1
            inner_end = i if depth > 0 else i - 1
            result[key] = _parse_gemma4_args(args_str[obj_start:inner_end])

        elif args_str[i] == "[":
            depth = 1
            arr_start = i + 1
            i += 1
            while i < n and depth > 0:
                if args_str[i : i + _DELIM_LEN] == STRING_DELIM:
                    i += _DELIM_LEN
                    next_delim = args_str.find(STRING_DELIM, i)
                    i = n if next_delim == -1 else next_delim + _DELIM_LEN
                    continue
                if args_str[i] == "[":
                    depth += 1
                elif args_str[i] == "]":
                    depth -= 1
                i += 1
            inner_end = i if depth > 0 else i - 1
            result[key] = _parse_gemma4_array(args_str[arr_start:inner_end])

        else:
            val_start = i
            while i < n and args_str[i] not in (",", "}", "]"):
                i += 1
            if i == val_start:
                break
            result[key] = args_str[val_start:i].strip()

    return result


def _parse_gemma4_array(arr_str: str) -> List[Any]:
    items: List[Any] = []
    i = 0
    n = len(arr_str)

    while i < n:
        while i < n and arr_str[i] in (" ", ",", "\n", "\t"):
            i += 1
        if i >= n:
            break

        if arr_str[i : i + _DELIM_LEN] == STRING_DELIM:
            i += _DELIM_LEN
            end_pos = arr_str.find(STRING_DELIM, i)
            if end_pos == -1:
                items.append(arr_str[i:])
                break
            items.append(arr_str[i:end_pos])
            i = end_pos + _DELIM_LEN

        elif arr_str[i] == "{":
            depth = 1
            obj_start = i + 1
            i += 1
            while i < n and depth > 0:
                if arr_str[i : i + _DELIM_LEN] == STRING_DELIM:
                    i += _DELIM_LEN
                    nd = arr_str.find(STRING_DELIM, i)
                    i = nd + _DELIM_LEN if nd != -1 else n
                    continue
                if arr_str[i] == "{":
                    depth += 1
                elif arr_str[i] == "}":
                    depth -= 1
                i += 1
            inner_end = i if depth > 0 else i - 1
            items.append(_parse_gemma4_args(arr_str[obj_start:inner_end]))

        elif arr_str[i] == "[":
            depth = 1
            sub_start = i + 1
            i += 1
            while i < n and depth > 0:
                if arr_str[i : i + _DELIM_LEN] == STRING_DELIM:
                    i += _DELIM_LEN
                    nd = arr_str.find(STRING_DELIM, i)
                    i = nd + _DELIM_LEN if nd != -1 else n
                    continue
                if arr_str[i] == "[":
                    depth += 1
                elif arr_str[i] == "]":
                    depth -= 1
                i += 1
            inner_end = i if depth > 0 else i - 1
            items.append(_parse_gemma4_array(arr_str[sub_start:inner_end]))

        else:
            val_start = i
            while i < n and arr_str[i] not in (",", "]"):
                i += 1
            if i == val_start:
                break
            items.append(arr_str[val_start:i].strip())

    return items


@register_parser("gemma4")
class Gemma4ToolCallParser(ToolCallParser):
    """Parser for Gemma 4 <|tool_call>call:name{…}<tool_call|> dumps."""

    CALL_RE = re.compile(
        re.escape(TOOL_CALL_START)
        + r"\s*call:([^{\s]+)\s*\{(.*?)\}"
        + re.escape(TOOL_CALL_END),
        re.DOTALL,
    )
    # Unclosed at end of string
    CALL_OPEN_RE = re.compile(
        re.escape(TOOL_CALL_START) + r"\s*call:([^{\s]+)\s*\{(.*)$",
        re.DOTALL,
    )

    def parse(self, text: str) -> ParseResult:
        if TOOL_CALL_START not in text:
            return text, None

        try:
            matches = self.CALL_RE.findall(text)
            if not matches:
                open_match = self.CALL_OPEN_RE.search(text)
                if open_match:
                    matches = [(open_match.group(1), open_match.group(2))]
            if not matches:
                return text, None

            tool_calls: List[ChatCompletionMessageToolCall] = []
            for func_name, args_str in matches:
                name = func_name.strip()
                if not name:
                    continue
                args = _parse_gemma4_args(args_str)
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=Function(
                            name=name,
                            arguments=json.dumps(args, ensure_ascii=False),
                        ),
                    )
                )

            if not tool_calls:
                return text, None

            first = text.find(TOOL_CALL_START)
            content = text[:first].strip() if first > 0 else None
            return content, tool_calls
        except Exception:
            return text, None
