"""
Kimi K2-Horizon (IFM) tool call parser.

Default XML:

    <ifm|tool_calls>
      <ifm|tool_call>get_weather
        <ifm|arg_key>city</ifm|arg_key>
        <ifm|arg_value>Paris</ifm|arg_value>
      </ifm|tool_call>
    </ifm|tool_calls>

JSON mode: each <ifm|tool_call> body is {"name":…,"arguments":{…}}.

Based on VLLM's K2HorizonToolParser.extract_tool_calls() (no schema coerce).
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser


@register_parser("k2_horizon")
class K2HorizonToolCallParser(ToolCallParser):
    """Parser for K2-Horizon IFM XML / JSON tool-call groups."""

    TOOL_CALLS_START = "<ifm|tool_calls>"
    TOOL_CALLS_END = "</ifm|tool_calls>"
    TOOL_CALL_START = "<ifm|tool_call>"
    TOOL_CALL_END = "</ifm|tool_call>"
    ARG_KEY_START = "<ifm|arg_key>"
    ARG_KEY_END = "</ifm|arg_key>"
    ARG_TYPE_START = "<ifm|arg_type>"
    ARG_TYPE_END = "</ifm|arg_type>"
    ARG_VALUE_START = "<ifm|arg_value>"
    ARG_VALUE_END = "</ifm|arg_value>"

    TOOL_CALL_RE = re.compile(
        re.escape(TOOL_CALL_START) + r"(.*?)" + re.escape(TOOL_CALL_END),
        re.DOTALL,
    )
    ARG_RE = re.compile(
        re.escape(ARG_KEY_START)
        + r"(.*?)"
        + re.escape(ARG_KEY_END)
        + r"\s*(?:"
        + re.escape(ARG_TYPE_START)
        + r"(.*?)"
        + re.escape(ARG_TYPE_END)
        + r"\s*)?"
        + re.escape(ARG_VALUE_START)
        + r"(.*?)"
        + re.escape(ARG_VALUE_END),
        re.DOTALL,
    )

    def _parse_json_call(self, body: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        try:
            raw_call = json.loads(body.strip())
        except json.JSONDecodeError:
            return None
        if not isinstance(raw_call, dict):
            return None
        name = raw_call.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        arguments = raw_call.get("arguments", {})
        if not isinstance(arguments, dict):
            return None
        return name.strip(), arguments

    def _parse_xml_call(self, body: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        first_arg = body.find(self.ARG_KEY_START)
        if first_arg == -1:
            name = body.strip()
            if not name:
                return None
            return name, {}
        name = body[:first_arg].strip()
        if not name:
            return None
        arguments: Dict[str, Any] = {}
        for match in self.ARG_RE.finditer(body, first_arg):
            arg_name = match.group(1).strip()
            if not arg_name:
                continue
            arguments[arg_name] = match.group(3)
        return name, arguments

    def parse(self, text: str) -> ParseResult:
        group_start = text.find(self.TOOL_CALLS_START)
        if group_start == -1:
            return text, None

        try:
            body_start = group_start + len(self.TOOL_CALLS_START)
            group_end = text.find(self.TOOL_CALLS_END, body_start)
            if group_end == -1:
                group_body = text[body_start:]
            else:
                group_body = text[body_start:group_end]

            matches = list(self.TOOL_CALL_RE.finditer(group_body))
            if not matches:
                return text, None

            tool_calls: List[ChatCompletionMessageToolCall] = []
            for match in matches:
                body = match.group(1)
                parsed = None
                stripped = body.strip()
                if stripped.startswith("{"):
                    parsed = self._parse_json_call(body)
                if parsed is None:
                    parsed = self._parse_xml_call(body)
                if parsed is None:
                    continue
                name, arguments = parsed
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        type="function",
                        function=Function(
                            name=name,
                            arguments=json.dumps(arguments, ensure_ascii=False),
                        ),
                    )
                )

            if not tool_calls:
                return text, None

            if group_end == -1:
                content = text[:group_start].strip() or None
            else:
                suffix = text[group_end + len(self.TOOL_CALLS_END) :]
                content = (text[:group_start] + suffix).strip() or None
            return content, tool_calls
        except Exception:
            return text, None
