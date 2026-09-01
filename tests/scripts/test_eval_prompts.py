# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Eval system prompt is the production chat builder plus the eval note."""

from plugin.framework.prompts import (
    TOOL_USAGE_PATTERNS,
    WRITER_REVIEW_MODES_RULES,
    get_chat_system_prompt_for_document,
)
from scripts.prompt_optimization.eval_prompts import (
    EVAL_HARNESS_NOTE,
    _stub_calc,
    _stub_draw,
    _stub_writer,
    get_calc_eval_chat_system_prompt,
    get_draw_eval_chat_system_prompt,
    get_writer_eval_chat_system_prompt,
)


def test_writer_eval_prompt_equals_production_plus_note() -> None:
    stub = _stub_writer()
    production = get_chat_system_prompt_for_document(stub, "", ctx=None)
    eval_p = get_writer_eval_chat_system_prompt()
    assert eval_p == get_chat_system_prompt_for_document(stub, EVAL_HARNESS_NOTE, ctx=None)
    assert eval_p.startswith(production)
    assert EVAL_HARNESS_NOTE in eval_p
    assert TOOL_USAGE_PATTERNS in eval_p
    assert WRITER_REVIEW_MODES_RULES in eval_p
    assert "delegate_to_specialized_writer_toolset" in eval_p
    assert "APPLY_DOCUMENT_CONTENT" in eval_p or "HTML" in eval_p
    assert "Only get_document_content" not in eval_p


def test_calc_draw_eval_prompts_use_production_builder() -> None:
    assert get_calc_eval_chat_system_prompt() == get_chat_system_prompt_for_document(
        _stub_calc(), EVAL_HARNESS_NOTE, ctx=None
    )
    assert get_draw_eval_chat_system_prompt() == get_chat_system_prompt_for_document(
        _stub_draw(), EVAL_HARNESS_NOTE, ctx=None
    )
    calc = get_calc_eval_chat_system_prompt()
    assert "write_formula_range" in calc
    assert EVAL_HARNESS_NOTE in calc
    draw = get_draw_eval_chat_system_prompt()
    assert "get_draw_tree" in draw
    assert EVAL_HARNESS_NOTE in draw
