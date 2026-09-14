"""
Shared DeepSeek DSML invoke/parameter extraction (V3.2 / V4 / V4.1).

vLLM engine parsers differ only in wrapper and spacing of the same tags:

    <｜DSML｜invoke name="func_name">
    <｜DSML｜parameter name="location" string="true">杭州</｜DSML｜parameter>
    </｜DSML｜invoke>
"""

import json
import re
import uuid
from typing import List, Pattern, Sequence

from plugin.contrib.tool_call_parsers.openai_compat import ChatCompletionMessageToolCall, Function

from plugin.contrib.tool_call_parsers import ParseResult

_DSML = "｜DSML｜"


def make_invoke_re(*, spaced: bool) -> Pattern:
    sep = r" " if spaced else r""
    return re.compile(
        rf"<{re.escape(_DSML)}{sep}invoke name=\"([^\"]+)\">(.*?)</{re.escape(_DSML)}{sep}invoke>",
        re.DOTALL,
    )


def make_param_re(*, spaced: bool) -> Pattern:
    sep = r" " if spaced else r""
    return re.compile(
        rf"<{re.escape(_DSML)}{sep}parameter\s+name=\"([^\"]+)\"\s+string=\"(true|false)\">"
        rf"(.*?)"
        rf"(?:</{re.escape(_DSML)}{sep}parameter>|(?=<{re.escape(_DSML)}{sep}parameter\s+name=))",
        re.DOTALL,
    )


def _convert_params(raw_args: str, param_re: Pattern) -> str:
    params: dict = {}
    for match in param_re.finditer(raw_args):
        name, is_str, value = match.group(1), match.group(2), match.group(3)
        if is_str == "true":
            params[name] = value
        else:
            try:
                params[name] = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                params[name] = value
    return json.dumps(params, ensure_ascii=False)


def parse_dsml(
    text: str,
    wrapper_starts: Sequence[str],
    invoke_re: Pattern,
    param_re: Pattern,
) -> ParseResult:
    start_idx = -1
    for token in wrapper_starts:
        idx = text.find(token)
        if idx >= 0 and (start_idx < 0 or idx < start_idx):
            start_idx = idx

    # Fallback: invoke without wrapper (truncated / variant dumps)
    if start_idx < 0:
        invoke_prefix = f"<{_DSML}"
        if invoke_prefix not in text or "invoke" not in text:
            return text, None
        start_idx = text.find(invoke_prefix)

    matches = invoke_re.findall(text)
    if not matches:
        return text, None

    tool_calls: List[ChatCompletionMessageToolCall] = []
    for func_name, raw_args in matches:
        name = func_name.strip()
        if not name:
            continue
        tool_calls.append(
            ChatCompletionMessageToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}",
                type="function",
                function=Function(
                    name=name,
                    arguments=_convert_params(raw_args, param_re),
                ),
            )
        )

    if not tool_calls:
        return text, None

    content = text[:start_idx].strip() if start_idx > 0 else None
    if content:
        # V4 may emit <think>…</think> before the wrapper; strip leftover close tags
        if content.endswith("</think>"):
            think_start = content.rfind("<think>")
            if think_start >= 0:
                content = content[:think_start].strip() or None
            else:
                content = content[: -len("</think>")].strip() or None
    return content, tool_calls
