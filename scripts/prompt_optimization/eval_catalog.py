# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core tool schemas for string eval — same ``get_schemas`` path as sidebar chat.

Headless ``ToolRegistry`` + module ``initialize`` (no ``plugin.main.bootstrap``).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from plugin.calc import CalcModule
from plugin.chatbot import ChatbotModule
from plugin.draw import DrawModule
from plugin.framework.config import init_config
from plugin.framework.service import ServiceRegistry
from plugin.framework.tool import ToolRegistry
from plugin.writer import WriterModule

_registry: ToolRegistry | None = None


def _headless_registry() -> ToolRegistry:
    """Writer + Calc + Draw + chatbot core tools, filtered later by doc_type."""
    global _registry
    if _registry is not None:
        return _registry

    init_config(MagicMock())
    services = ServiceRegistry()
    services.register("config", MagicMock())
    services.register("document", MagicMock())
    services.register("events", MagicMock())
    tools = ToolRegistry(services)
    services.register("tools", tools)

    WriterModule().initialize(services)
    CalcModule().initialize(services)
    DrawModule().initialize(services)
    ChatbotModule().initialize(services)
    tools.auto_discover_package("plugin.doc")

    _registry = tools
    return tools


def build_eval_tool_schemas(
    *, kind: str, active_domain: str | None = None
) -> list[dict[str, Any]]:
    """OpenAI function schemas for writer / draw / calc — same filter as sidebar.

    ``active_domain`` matches production specialized mode (shapes, ranges, …).
    """
    doc_type = kind if kind in ("writer", "draw", "calc") else "writer"
    kwargs: dict[str, Any] = {
        "doc_type": doc_type,
        "filter_doc_type": True,
    }
    if active_domain:
        kwargs["active_domain"] = active_domain
        kwargs["exclude_tiers"] = ()
    return _headless_registry().get_schemas("openai", **kwargs)
