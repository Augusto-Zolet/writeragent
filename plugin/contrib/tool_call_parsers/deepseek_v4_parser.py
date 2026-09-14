"""
DeepSeek V4 / V4.1 tool call parsers.

V4 uses a tool_calls wrapper (plus toolcalls / tool variants) and optional <think>:

    <think>…</think>
    <｜DSML｜tool_calls>
    <｜DSML｜invoke name="func_name">…</｜DSML｜invoke>
    </｜DSML｜tool_calls>

V4.1 is the same shape with a space after ｜DSML｜ (tokenizer split):
    <｜DSML｜ calls>  <｜DSML｜ invoke name="…">  <｜DSML｜ parameter …>

Based on VLLM's parser/deepseek_v4.py and parser/deepseek_v41.py
"""

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser
from plugin.contrib.tool_call_parsers.deepseek_dsml import (
    make_invoke_re,
    make_param_re,
    parse_dsml,
)


@register_parser("deepseek_v4")
class DeepSeekV4ToolCallParser(ToolCallParser):
    """Parser for DeepSeek V4 DSML tool calls."""

    WRAPPERS = (
        "<｜DSML｜tool_calls>",
        "<｜DSML｜toolcalls>",
        "<｜DSML｜tool>",
    )
    INVOKE_RE = make_invoke_re(spaced=False)
    PARAM_RE = make_param_re(spaced=False)

    def parse(self, text: str) -> ParseResult:
        try:
            return parse_dsml(text, self.WRAPPERS, self.INVOKE_RE, self.PARAM_RE)
        except Exception:
            return text, None


@register_parser("deepseek_v41")
@register_parser("deepseek_v4_1")
class DeepSeekV41ToolCallParser(ToolCallParser):
    """Parser for DeepSeek V4.1 spaced-DSML tool calls."""

    WRAPPERS = (
        "<｜DSML｜ calls>",
        "<｜DSML｜calls>",
    )
    INVOKE_RE = make_invoke_re(spaced=True)
    PARAM_RE = make_param_re(spaced=True)

    def parse(self, text: str) -> ParseResult:
        try:
            return parse_dsml(text, self.WRAPPERS, self.INVOKE_RE, self.PARAM_RE)
        except Exception:
            return text, None
