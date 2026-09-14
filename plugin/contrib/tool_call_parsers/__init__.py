"""
Client-side Hermes <tool_call> extractor.

Used when the HTTP response has assistant content but no structured tool_calls.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from .openai_compat import (
    ChatCompletionMessageToolCall as ChatCompletionMessageToolCall,
)

# Type alias for parser return value
ParseResult = Tuple[Optional[str], Optional[List[dict]]]


class ToolCallParser(ABC):
    """Base class for tool call parsers."""

    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        """
        Parse raw model output text for tool calls.

        Returns:
            Tuple of (content, tool_calls) where:
            - content: text with tool call markup stripped, or None
            - tool_calls: list of ChatCompletionMessageToolCall objects, or None
        """
        raise NotImplementedError


class _WrappedParser(ToolCallParser):
    def __init__(self, parser: ToolCallParser):
        self.parser = parser

    def parse(self, text: str) -> ParseResult:
        content, tool_calls = self.parser.parse(text)
        if tool_calls:
            tool_calls = [
                tc.to_dict() if hasattr(tc, "to_dict") else tc  # type: ignore[attr-defined]
                for tc in tool_calls
            ]
        return content, tool_calls


from .hermes_parser import HermesToolCallParser  # noqa: E402, F401


def get_parser() -> ToolCallParser:
    """Return the Hermes <tool_call> parser."""
    return _WrappedParser(HermesToolCallParser())


def get_parser_for_model(model_name: str) -> Optional[ToolCallParser]:
    """Return the Hermes parser when a model id is present."""
    if not model_name:
        return None
    return get_parser()
