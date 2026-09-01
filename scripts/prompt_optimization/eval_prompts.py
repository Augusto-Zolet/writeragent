# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Eval-harness system prompts: production chat builder + one eval footnote.

Does not query the tool registry. Schemas live in ``eval_catalog``.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from plugin.framework.prompts import get_chat_system_prompt_for_document

# The only eval-specific addendum. Production already appends additional_instructions.
EVAL_HARNESS_NOTE = (
    "[Eval harness] Core tools match chat. Tools the string harness does not "
    "implement return status=error code=unsupported_in_eval — recover or finish "
    "without them. Do not call domain=python."
)


def _stub_doc(service: str) -> Any:
    """UNO-shaped stub so ``is_writer`` / ``is_calc`` / ``is_draw`` work without soffice."""
    doc = MagicMock()
    doc.supportsService = lambda svc, want=service: svc == want
    return doc


def _stub_writer() -> Any:
    return _stub_doc("com.sun.star.text.TextDocument")


def _stub_calc() -> Any:
    return _stub_doc("com.sun.star.sheet.SpreadsheetDocument")


def _stub_draw() -> Any:
    return _stub_doc("com.sun.star.drawing.DrawingDocument")


def get_writer_eval_chat_system_prompt() -> str:
    return get_chat_system_prompt_for_document(_stub_writer(), EVAL_HARNESS_NOTE, ctx=None)


def get_calc_eval_chat_system_prompt() -> str:
    return get_chat_system_prompt_for_document(_stub_calc(), EVAL_HARNESS_NOTE, ctx=None)


def get_draw_eval_chat_system_prompt() -> str:
    return get_chat_system_prompt_for_document(_stub_draw(), EVAL_HARNESS_NOTE, ctx=None)


def get_eval_system_prompt(task_id: str = "") -> str:
    from dataset import task_kind

    kind = task_kind(task_id)
    if kind == "calc":
        return get_calc_eval_chat_system_prompt()
    if kind == "draw":
        return get_draw_eval_chat_system_prompt()
    return get_writer_eval_chat_system_prompt()
