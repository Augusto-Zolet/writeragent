"""
FunctionGemma tool call parser.

    <start_function_call>call:func_name{param:<escape>value<escape>}<end_function_call>

Based on VLLM's FunctionGemmaToolParser.extract_tool_calls()
"""

import json
import re
import uuid
from typing import List

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser


@register_parser("functiongemma")
class FunctionGemmaToolCallParser(ToolCallParser):
    """Parser for Google FunctionGemma call:name{param:<escape>…} dumps."""

    START_TOKEN = "<start_function_call>"
    TOOL_CALL_REGEX = re.compile(
        r"<start_function_call>call:(\w+)\{(.*?)\}<end_function_call>"
        r"|<start_function_call>call:(\w+)\{(.*)",
        re.DOTALL,
    )
    ARG_REGEX = re.compile(r"(\w+):<escape>(.*?)<escape>", re.DOTALL)

    def parse(self, text: str) -> ParseResult:
        if self.START_TOKEN not in text:
            return text, None

        try:
            matches = self.TOOL_CALL_REGEX.findall(text)
            if not matches:
                return text, None

            tool_calls: List[ChatCompletionMessageToolCall] = []
            for match in matches:
                func_name = match[0] if match[0] else match[2]
                args_str = match[1] if match[1] else match[3]
                if not func_name:
                    continue
                arguments: dict = {}
                for key, value in self.ARG_REGEX.findall(args_str):
                    try:
                        arguments[key] = json.loads(value)
                    except json.JSONDecodeError:
                        arguments[key] = value
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=Function(
                            name=func_name,
                            arguments=json.dumps(arguments, ensure_ascii=False),
                        ),
                    )
                )

            if not tool_calls:
                return text, None

            first = text.find(self.START_TOKEN)
            content = text[:first].strip() if first > 0 else None
            return content, tool_calls
        except Exception:
            return text, None
