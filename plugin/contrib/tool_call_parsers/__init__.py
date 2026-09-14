"""
Tool Call Parser Registry

Client-side parsers that extract structured tool_calls from raw model output text.
Used in Phase 2 (VLLM server type) where ManagedServer's /generate endpoint returns
raw text without tool call parsing.

Each parser is a standalone reimplementation of the corresponding VLLM parser's
non-streaming extract_tool_calls() logic. No VLLM dependency -- only standard library
(re, json, uuid) and openai types.

Usage:
    from . import get_parser

    parser = get_parser("hermes")
    content, tool_calls = parser.parse(raw_model_output)
    # content = text with tool call markup stripped
    # tool_calls = list of ChatCompletionMessageToolCall objects, or None
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
    # added wrapper to return dicts
    def parse_to_dict(self, text: str) -> None:
        pass
    """
    Base class for tool call parsers.

    Each parser knows how to extract structured tool_calls from a specific
    model family's raw output text format.
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
    """
    Decorator to register a parser class under a given name.

    Usage:
        @register_parser("hermes")
        class HermesToolCallParser(ToolCallParser):
            ...
    """

    def decorator(cls: Type[ToolCallParser]) -> Type[ToolCallParser]:
        PARSER_REGISTRY[name] = cls
        return cls

    return decorator



class _WrappedParser(ToolCallParser):
    def __init__(self, parser): self.parser = parser
    def parse(self, text: str) -> ParseResult:
        content, tool_calls = self.parser.parse(text)
        if tool_calls:
            tool_calls = [tc.to_dict() if hasattr(tc, 'to_dict') else tc for tc in tool_calls]
        return content, tool_calls

def get_parser(name: str) -> ToolCallParser:

    """
    Get a parser instance by name.

    Args:
        name: Parser name (e.g., "hermes", "mistral", "llama3_json")

    Returns:
        Instantiated parser

    Raises:
        KeyError: If parser name is not found in registry
    """
    if name not in PARSER_REGISTRY:
        available = sorted(PARSER_REGISTRY.keys())
        raise KeyError(
            f"Tool call parser '{name}' not found. Available parsers: {available}"
        )
    return _WrappedParser(PARSER_REGISTRY[name]())


def list_parsers() -> List[str]:
    """Return sorted list of registered parser names."""
    return sorted(PARSER_REGISTRY.keys())


# Import all parser modules to trigger registration via @register_parser decorators
# Each module registers itself when imported
from .hermes_parser import HermesToolCallParser  # noqa: E402, F401
from .longcat_parser import LongcatToolCallParser  # noqa: E402, F401
from .mistral_parser import MistralToolCallParser  # noqa: E402, F401
from .llama_parser import LlamaToolCallParser  # noqa: E402, F401
from .qwen_parser import QwenToolCallParser  # noqa: E402, F401
from .deepseek_v3_parser import DeepSeekV3ToolCallParser  # noqa: E402, F401
from .deepseek_v3_1_parser import DeepSeekV31ToolCallParser  # noqa: E402, F401
from .deepseek_v32_parser import DeepSeekV32ToolCallParser  # noqa: E402, F401
from .deepseek_v4_parser import (  # noqa: E402, F401
    DeepSeekV4ToolCallParser,
    DeepSeekV41ToolCallParser,
)
from .kimi_k2_parser import KimiK2ToolCallParser  # noqa: E402, F401
from .kimi_k3_parser import KimiK3ToolCallParser  # noqa: E402, F401
from .k2_horizon_parser import K2HorizonToolCallParser  # noqa: E402, F401
from .glm45_parser import Glm45ToolCallParser  # noqa: E402, F401
from .glm47_parser import Glm47ToolCallParser  # noqa: E402, F401
from .qwen3_coder_parser import Qwen3CoderToolCallParser  # noqa: E402, F401
from .minimax_m2_parser import MinimaxM2ToolCallParser  # noqa: E402, F401
from .functiongemma_parser import FunctionGemmaToolCallParser  # noqa: E402, F401
from .gemma4_parser import Gemma4ToolCallParser  # noqa: E402, F401
from .llama4_pythonic_parser import Llama4PythonicToolCallParser  # noqa: E402, F401


def resolve_parser_name(model_name: str) -> Optional[str]:
    """Map a model id to a registered parser name. Most-specific match wins."""
    if not model_name:
        return None
    model_name = model_name.lower()

    if "hermes" in model_name:
        return "hermes"
    if (
        "qwen3-coder" in model_name
        or "qwen3_coder" in model_name
        or "qwen3coder" in model_name
    ):
        return "qwen3_coder"
    if "qwen" in model_name:
        return "hermes"
    if "deepseek" in model_name:
        if "v4.1" in model_name or "v41" in model_name:
            return "deepseek_v41"
        if "v4" in model_name:
            return "deepseek_v4"
        if "v3.2" in model_name or "v32" in model_name:
            return "deepseek_v32"
        if "v3.1" in model_name or "v31" in model_name:
            return "deepseek_v31"
        return "deepseek_v3"
    if "minimax" in model_name:
        return "minimax_m2"
    if "kimi" in model_name:
        if "k3" in model_name:
            return "kimi_k3"
        if "horizon" in model_name:
            return "k2_horizon"
        return "kimi_k2"
    if "glm" in model_name or "z-ai" in model_name or "zhipu" in model_name:
        return "glm47"
    if "longcat" in model_name:
        return "longcat"
    if "functiongemma" in model_name:
        return "functiongemma"
    if "gemma-4" in model_name or "gemma4" in model_name or "gemma_4" in model_name:
        return "gemma4"
    if "mistral" in model_name:
        return "mistral"
    if "llama" in model_name:
        if "pythonic" in model_name:
            return "llama4_pythonic"
        return "llama3_json"
    return None


def get_parser_for_model(model_name: str) -> Optional[ToolCallParser]:
    """Identify and return a parser instance based on the model string."""
    name = resolve_parser_name(model_name)
    if name is None:
        return None
    try:
        return get_parser(name)
    except KeyError:
        return None
