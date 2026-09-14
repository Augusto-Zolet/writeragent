"""
GLM 4.7 tool call parser.

vLLM maps both glm45 and glm47 to the same extract format
(no required newline, zero-arg legal). This class is a registered alias.
"""

from plugin.contrib.tool_call_parsers import register_parser
from plugin.contrib.tool_call_parsers.glm45_parser import Glm45ToolCallParser


@register_parser("glm47")
class Glm47ToolCallParser(Glm45ToolCallParser):
    """Parser for GLM 4.7; same tags as GLM 4.5."""

    pass
