"""
MiniMax M2 tool call parser.

    <minimax:tool_call><invoke name="get_weather">
    <parameter name="city">Seattle</parameter>
    </invoke></minimax:tool_call>

Based on VLLM's parser/minimax_m2.py
"""

import json
import re
import uuid
from typing import List

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser


@register_parser("minimax_m2")
class MinimaxM2ToolCallParser(ToolCallParser):
    """Parser for MiniMax M2 XML invoke/parameter tool calls."""

    START_TOKEN = "<minimax:tool_call>"

    INVOKE_RE = re.compile(
        r"<invoke\s+name\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))\s*>(.*?)</invoke>",
        re.DOTALL,
    )
    PARAM_RE = re.compile(
        r"<\s*parameter\s+name\s*=\s*"
        r"(?:\"(?P<dq_name>[^\"]*)\"|'(?P<sq_name>[^']*)'|(?P<bare_name>[^>\s]+))"
        r"\s*>"
        r"(?P<value>.*?)"
        r"(?:<\s*/\s*parameter\s*>|(?=<\s*parameter\s+name\s*=))",
        re.DOTALL,
    )

    def parse(self, text: str) -> ParseResult:
        if self.START_TOKEN not in text and "<invoke" not in text:
            return text, None

        try:
            matches = self.INVOKE_RE.findall(text)
            if not matches:
                return text, None

            tool_calls: List[ChatCompletionMessageToolCall] = []
            for dq_name, sq_name, bare_name, raw_args in matches:
                func_name = (dq_name or sq_name or bare_name or "").strip()
                if not func_name:
                    continue
                params = {}
                for match in self.PARAM_RE.finditer(raw_args):
                    name = (
                        match.group("dq_name")
                        or match.group("sq_name")
                        or match.group("bare_name")
                        or ""
                    ).strip()
                    if name:
                        params[name] = match.group("value")
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=Function(
                            name=func_name,
                            arguments=json.dumps(params, ensure_ascii=False),
                        ),
                    )
                )

            if not tool_calls:
                return text, None

            first = text.find(self.START_TOKEN)
            if first < 0:
                first = text.find("<invoke")
            content = text[:first].strip() if first > 0 else None
            return content, tool_calls
        except Exception:
            return text, None
