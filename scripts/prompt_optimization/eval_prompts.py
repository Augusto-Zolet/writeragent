# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Writer eval-harness system prompt for offline DSPy (`scripts/prompt_optimization`).

HTML / apply_document_content rules stay in plugin.framework.prompts; this module
describes only the tools wired in the eval harness.
"""
from __future__ import annotations

from plugin.framework.prompts import (
    SIDEBAR_VS_DOCUMENT,
    TRANSLATION_RULES,
    WRITER_APPLY_DOCUMENT_HTML_RULES,
)


WRITER_EVAL_TOOLS_SECTION = """TOOLS (eval harness):
- apply_document_content: Insert or replace HTML in the document (parameters and format — see APPLY_DOCUMENT_CONTENT AND HTML below).
- get_document_content: Read document (full/selection/range) as HTML.
- find_text: Find text in the document (JSON ranges)."""

WRITER_EVAL_SCOPE = (
    "[Eval harness] Only get_document_content, apply_document_content, and find_text are registered. "
    "Do not use web research, delegate_to_specialized_writer_toolset, search_in_document, apply_style, or add_comment."
)

WRITER_EVAL_TOOL_USAGE_PATTERNS = """TOOL USAGE PATTERNS (eval harness):
- Use find_text to locate passages; use apply_document_content (often with old_content) to replace HTML.
- Re-read with get_document_content after substantive edits if needed."""


def get_writer_eval_chat_system_prompt() -> str:
    """Writer chat-style system prompt for offline DSPy eval (`scripts/prompt_optimization`).

    Reuses the same HTML / apply_document_content rules as production chat
    (`WRITER_APPLY_DOCUMENT_HTML_RULES`, `TRANSLATION_RULES`) but describes only tools implemented in the
    eval harness: ``get_document_content``, ``apply_document_content``, ``find_text``.
    Omits web research, specialized delegation, memory, and tools not wired in ``tools_lo``.
    """
    return "\n\n".join([
        SIDEBAR_VS_DOCUMENT,
        WRITER_EVAL_SCOPE,
        WRITER_EVAL_TOOLS_SECTION,
        TRANSLATION_RULES,
        WRITER_EVAL_TOOL_USAGE_PATTERNS,
        WRITER_APPLY_DOCUMENT_HTML_RULES,
    ])
