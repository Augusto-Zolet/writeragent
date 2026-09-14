"""
Kimi K3 (XTML) tool call parser.

    <|open|>tools<|sep|>
      <|open|>call tool="python" index="1"<|sep|>
        <|open|>argument key="code" type="string"<|sep|>print(1)<|close|>argument<|sep|>
      <|close|>call<|sep|>
    <|close|>tools<|sep|>

Reply lives in a sibling <|open|>response<|sep|>…<|close|>response<|sep|>.
Based on VLLM's KimiK3ToolParser.extract_tool_calls() (non-streaming path only).
"""

import json
import re
import uuid
from typing import Dict, List, Optional

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser

_O = r"<\|open\|>"
_C = r"<\|close\|>"
_S = r"<\|sep\|>"
_TEXT_UNTIL_SEP = r"(?:(?!" + _S + r").)*?"


@register_parser("kimi_k3")
class KimiK3ToolCallParser(ToolCallParser):
    """Parser for Kimi K3 XTML tools/response channels."""

    _TOOLS_OPEN_RE = re.compile(_O + r"\s*tools\s*" + _S)
    _TOOLS_CLOSE_RE = re.compile(_C + r"\s*tools\s*" + _S)
    _RESPONSE_OPEN_RE = re.compile(_O + r"\s*response\s*" + _S)
    _RESPONSE_CLOSE_RE = re.compile(_C + r"\s*response\s*" + _S)
    _MESSAGE_CLOSE_RE = re.compile(_C + r"\s*message\s*" + _S)
    _CALL_RE = re.compile(
        _O
        + r"\s*call\s+(?P<attrs>"
        + _TEXT_UNTIL_SEP
        + r")"
        + _S
        + r"(?P<body>.*?)"
        + _C
        + r"\s*call\s*"
        + _S,
        re.DOTALL,
    )
    _ARG_RE = re.compile(
        _O
        + r"\s*argument\s+(?P<attrs>"
        + _TEXT_UNTIL_SEP
        + r")"
        + _S
        + r"(?P<val>.*?)"
        + _C
        + r"\s*argument\s*"
        + _S,
        re.DOTALL,
    )
    _ATTR_RE = re.compile(r'(?P<k>\w+)="(?P<v>[^"]*)"')
    _RESPONSE_RE = re.compile(
        _O + r"\s*response\s*" + _S + r"(?P<c>.*?)" + _C + r"\s*response\s*" + _S,
        re.DOTALL,
    )

    def _attrs(self, s: str) -> Dict[str, str]:
        return {
            m["k"]: m["v"].replace("&quot;", '"').replace("&amp;", "&")
            for m in self._ATTR_RE.finditer(s)
        }

    def _decode_call(self, attrs: str, body: str) -> Optional[ChatCompletionMessageToolCall]:
        call_attrs = self._attrs(attrs)
        tool_name = call_attrs.get("tool", "")
        arguments: dict = {}
        for arg_match in self._ARG_RE.finditer(body):
            arg_attrs = self._attrs(arg_match["attrs"])
            key = arg_attrs.get("key", "")
            arg_type = arg_attrs.get("type", "string")
            raw_value = arg_match["val"]
            if arg_type == "string":
                arguments[key] = raw_value
            else:
                try:
                    arguments[key] = json.loads(raw_value)
                except json.JSONDecodeError:
                    arguments[key] = raw_value
        if not tool_name:
            return None
        return ChatCompletionMessageToolCall(
            id=f"call_{uuid.uuid4().hex[:8]}",
            type="function",
            function=Function(
                name=tool_name,
                arguments=json.dumps(arguments, ensure_ascii=False),
            ),
        )

    def _strip_response_content(self, text: str) -> Optional[str]:
        m_open = self._RESPONSE_OPEN_RE.search(text)
        if m_open is not None:
            m_close = self._RESPONSE_CLOSE_RE.search(text, m_open.end())
            if m_close is not None:
                text = text[m_open.end() : m_close.start()]
            else:
                text = text[m_open.end() :]
        else:
            text = self._RESPONSE_CLOSE_RE.sub("", text)
        text = self._MESSAGE_CLOSE_RE.sub("", text)
        return text or None

    def _content(self, model_output: str, before: str) -> Optional[str]:
        m = self._RESPONSE_RE.search(model_output)
        if m is not None:
            return m["c"] or None
        return self._strip_response_content(before)

    def parse(self, text: str) -> ParseResult:
        m_open = self._TOOLS_OPEN_RE.search(text)
        if m_open is None:
            content = self._content(text, text)
            return content if content is not None else text, None

        try:
            before = text[: m_open.start()]
            start = m_open.end()
            m_close = self._TOOLS_CLOSE_RE.search(text, start)
            section = text[start:] if m_close is None else text[start : m_close.start()]

            tool_calls: List[ChatCompletionMessageToolCall] = []
            for match in self._CALL_RE.finditer(section):
                tc = self._decode_call(match["attrs"], match["body"])
                if tc is not None:
                    tool_calls.append(tc)

            if not tool_calls:
                content = self._content(text, before)
                return content if content is not None else text, None

            return self._content(text, before), tool_calls
        except Exception:
            return text, None
