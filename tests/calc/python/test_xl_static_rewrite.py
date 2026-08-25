# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for save-time ``xl("A1")`` → polymorphic ``data`` / ``data[i]`` rewrite."""

from __future__ import annotations

from unittest.mock import patch

from plugin.calc.python.editor import _apply_cell_save, _maybe_apply_xl_static_rewrite
from plugin.calc.python.formula_edit import parse_python_formula
from plugin.calc.python.xl_static_rewrite import (
    apply_xl_static_rewrite,
    is_static_a1_literal,
    migrate_bare_data_to_index0,
    normalize_range_address,
)
from plugin.tests.testing_utils import CalcCellStub, CalcDocStub


def test_is_static_a1_literal_accepts_common_forms():
    assert is_static_a1_literal("A1")
    assert is_static_a1_literal("A1:A10")
    assert is_static_a1_literal("$A$1:$B$10")
    assert is_static_a1_literal("Sheet1.A1:B2")
    assert is_static_a1_literal("'My Sheet'.A1")
    assert is_static_a1_literal("Sheet1!A1:A2")


def test_apply_xl_static_rewrite_null_byte_is_issue_not_crash():
    """CPython rejects NUL in source (ValueError); must not leak TypeError/ValueError."""
    res = apply_xl_static_rewrite("\x00")
    assert res.changed is False
    assert res.issues
    assert "not parseable" in res.issues[0] or "syntax" in res.issues[0].lower()


def test_is_static_a1_literal_rejects_non_addresses():
    assert not is_static_a1_literal("%P2%")
    assert not is_static_a1_literal("Table1")
    assert not is_static_a1_literal("")
    assert not is_static_a1_literal("not a range")


def test_normalize_range_address_strips_dollars_and_excel_bang():
    assert normalize_range_address("$A$1:$A$10") == "A1:A10"
    assert normalize_range_address("Sheet1!B2") == "Sheet1.B2"


def test_rewrite_single_range_headers_true():
    result = apply_xl_static_rewrite('df = xl("A1:A10", headers=True)')
    assert result.changed
    assert result.issues == []
    assert result.data_args == ["A1:A10"]
    assert result.code == "df = data.to_pandas()"


def test_rewrite_headers_false_and_omit_multi():
    code = 'a = xl("A1")\nb = xl("B1:B2", headers=False)\n'
    result = apply_xl_static_rewrite(code)
    assert result.changed
    assert result.data_args == ["A1", "B1:B2"]
    assert "a = data[0]\n" in result.code
    assert "b = data[1].to_pandas(header_row=None)" in result.code


def test_rewrite_dedups_identical_addresses():
    code = 'x = xl("A1:A10") + xl("A1:A10")'
    result = apply_xl_static_rewrite(code)
    assert result.data_args == ["A1:A10"]
    assert result.code == "x = data + data"


def test_rewrite_keeps_existing_data_args_first():
    result = apply_xl_static_rewrite('x = xl("C1")', existing_data_args=["A1:A5"])
    assert result.data_args == ["A1:A5", "C1"]
    assert result.code == "x = data[1]"


def test_rewrite_reuses_existing_matching_address():
    result = apply_xl_static_rewrite(
        'x = xl("$A$1:$A$5")',
        existing_data_args=["A1:A5"],
    )
    assert result.data_args == ["A1:A5"]
    assert result.code == "x = data"


def test_rewrite_leaves_percent_p_tokens_alone():
    code = 'x = xl("%P2%")\ny = xl("A1")\n'
    result = apply_xl_static_rewrite(code)
    assert result.changed
    assert 'xl("%P2%")' in result.code
    assert "y = data" in result.code


def test_migrate_bare_data_to_index0():
    src = "df = data.to_pandas()\nx = data\ny = data[2]\n"
    out = migrate_bare_data_to_index0(src)
    assert "df = data[0].to_pandas()" in out
    assert "x = data[0]\n" in out
    assert "y = data[2]\n" in out  # already indexed — leave alone


def test_rewrite_one_to_many_migrates_prior_data():
    # Prior sugar left bare data; adding a second xl grows bindings.
    code = 'df = data.to_pandas()\nx = xl("C1")\n'
    result = apply_xl_static_rewrite(code, existing_data_args=["A1:A10"])
    assert result.data_args == ["A1:A10", "C1"]
    assert "df = data[0].to_pandas()" in result.code
    assert "x = data[1]" in result.code


def test_rewrite_fail_closed_on_dynamic():
    result = apply_xl_static_rewrite('x = xl(f"A1:A{n}")')
    assert not result.changed
    assert any("dynamic" in i for i in result.issues)


def test_rewrite_fail_closed_on_named_table():
    result = apply_xl_static_rewrite('x = xl("Table1")')
    assert not result.changed
    assert result.issues


def test_rewrite_no_xl_unchanged():
    result = apply_xl_static_rewrite("result = np.sum(data)", existing_data_args=["A1"])
    assert not result.changed
    assert result.code == "result = np.sum(data)"
    assert result.data_args == ["A1"]


def test_maybe_apply_skipped_when_flag_off():
    with patch("plugin.calc.python.editor.get_config", return_value=False):
        out = _maybe_apply_xl_static_rewrite('df = xl("A1:A10", headers=True)', "")
    assert out == ('df = xl("A1:A10", headers=True)', "")


def test_maybe_apply_rewrites_when_flag_on():
    with patch("plugin.calc.python.editor.get_config", return_value=True):
        out = _maybe_apply_xl_static_rewrite('df = xl("A1:A10", headers=True)', "")
    assert not isinstance(out, dict)
    code, binding = out
    assert code == "df = data.to_pandas()"
    assert binding == "A1:A10"


def test_maybe_apply_errors_on_dynamic_when_flag_on():
    with patch("plugin.calc.python.editor.get_config", return_value=True):
        out = _maybe_apply_xl_static_rewrite('x = xl(name)', "")
    assert isinstance(out, dict)
    assert out["type"] == "error"


def test_apply_cell_save_lifts_xl_when_flag_on():
    doc = CalcDocStub()
    cell = CalcCellStub()
    with patch("plugin.calc.python.editor.get_config", return_value=True):
        result = _apply_cell_save(
            doc,
            cell,
            parsed_parts=None,
            new_code='df = xl("D1:D10", headers=True)\nresult = len(df)',
            save_as_plain=False,
            data_binding_text="",
        )
    assert result["ok"] is True
    formula = cell.getFormula()
    assert "D1:D10" in formula
    assert "data.to_pandas()" in formula
    assert "xl(" not in formula


def test_apply_cell_save_merges_with_parsed_data_suffix():
    doc = CalcDocStub()
    cell = CalcCellStub()
    parts = parse_python_formula('=PY("x"; A1:A5)')
    assert parts is not None
    with patch("plugin.calc.python.editor.get_config", return_value=True):
        result = _apply_cell_save(
            doc,
            cell,
            parsed_parts=parts,
            new_code='y = xl("C1")',
            save_as_plain=False,
            data_binding_text=None,
        )
    assert result["ok"] is True
    formula = cell.getFormula()
    assert "A1:A5" in formula
    assert "C1" in formula
    assert "data[1]" in formula
