"""
DeepSeek V3.2 tool call parser.

DSML with a function_calls wrapper (no <think> tags):

    <｜DSML｜function_calls>
    <｜DSML｜invoke name="func_name">
    <｜DSML｜parameter name="location" string="true">杭州</｜DSML｜parameter>
    </｜DSML｜invoke>
    </｜DSML｜function_calls>

Based on VLLM's DeepSeekV32EngineToolParser / parser/deepseek_v32.py
"""

from plugin.contrib.tool_call_parsers import ParseResult, ToolCallParser, register_parser
from plugin.contrib.tool_call_parsers.deepseek_dsml import (
    make_invoke_re,
    make_param_re,
    parse_dsml,
)


@register_parser("deepseek_v32")
class DeepSeekV32ToolCallParser(ToolCallParser):
    """Parser for DeepSeek V3.2 DSML tool calls."""

    WRAPPERS = ("<｜DSML｜function_calls>",)
    INVOKE_RE = make_invoke_re(spaced=False)
    PARAM_RE = make_param_re(spaced=False)

    def parse(self, text: str) -> ParseResult:
        try:
            return parse_dsml(text, self.WRAPPERS, self.INVOKE_RE, self.PARAM_RE)
        except Exception:
            return text, None
