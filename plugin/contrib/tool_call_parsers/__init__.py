"""
Tool Call Parser Registry

Client-side parser that extracts structured tool_calls from model output text
formatted with Hermes <tool_call> tags.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Type

from .openai_compat import (
    ChatCompletionMessageToolCall as ChatCompletionMessageToolCall,
)

logger = logging.getLogger(__name__)

# Type alias for parser return value
ParseResult = Tuple[Optional[str], Optional[List[dict]]]


class ToolCallParser(ABC):
    def parse_to_dict(self, text: str) -> None:
        pass

    """
    Base class for tool call parsers.
    """

    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        """
        Parse raw model output text for tool calls.

        Args:
            text: Raw decoded text from the model's completion

        Returns:
            Tuple of (content, tool_calls) where:
            - content: text with tool call markup stripped (the message 'content' field),
                       or None if the entire output was tool calls
            - tool_calls: list of ChatCompletionMessageToolCall objects,
                          or None if no tool calls were found
        """
        raise NotImplementedError


# Global parser registry: name -> parser class
PARSER_REGISTRY: Dict[str, Type[ToolCallParser]] = {}


def register_parser(name: str):
    """Decorator to register a parser class under a given name."""

    def decorator(cls: Type[ToolCallParser]) -> Type[ToolCallParser]:
        PARSER_REGISTRY[name] = cls
        return cls

    return decorator


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


def get_parser(name: str = "hermes") -> ToolCallParser:
    """
    Get a parser instance by name.

    Defaults to Hermes parser if available.
    """
    cls = PARSER_REGISTRY.get(name) or PARSER_REGISTRY.get("hermes")
    if cls is None:
        available = sorted(PARSER_REGISTRY.keys())
        raise KeyError(
            f"Tool call parser '{name}' not found. Available parsers: {available}"
        )
    return _WrappedParser(cls())


def list_parsers() -> List[str]:
    """Return sorted list of registered parser names."""
    return sorted(PARSER_REGISTRY.keys())


# Import Hermes parser to trigger registration via @register_parser decorator
from .hermes_parser import HermesToolCallParser  # noqa: E402, F401

# Register common aliases
PARSER_REGISTRY["qwen"] = HermesToolCallParser
PARSER_REGISTRY["default"] = HermesToolCallParser


def resolve_parser_name(model_name: str) -> Optional[str]:
    """Map a model id to a registered parser name. Hermes handles <tool_call> tags."""
    if not model_name:
        return None
    return "hermes"


def get_parser_for_model(model_name: str) -> Optional[ToolCallParser]:
    """Identify and return a parser instance based on the model string."""
    if not model_name:
        return None
    try:
        return get_parser("hermes")
    except KeyError:
        return None
