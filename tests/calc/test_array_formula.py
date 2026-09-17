# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure unit tests for Calc array-formula detection (no soffice)."""

from __future__ import annotations

from plugin.calc.array_formula import returns_array, top_level_calls


def test_sum_of_filter_is_scalar_top_level():
    assert top_level_calls("=SUM(FILTER(A1:A9;B1:B9>0))") == ["SUM"]
    assert returns_array("=SUM(FILTER(A1:A9;B1:B9>0))") is False


def test_sort_of_filter_is_array():
    assert top_level_calls("=SORT(FILTER(A1:A9;B1:B9>0))") == ["SORT"]
    assert returns_array("=SORT(FILTER(A1:A9;B1:B9>0))") is True


def test_plain_arithmetic_is_not_array():
    assert returns_array("=A1+A2") is False
    assert top_level_calls("=A1+A2") == []


def test_quoted_filter_is_not_a_call():
    assert top_level_calls('="FILTER("') == []
    assert returns_array('="FILTER("') is False


def test_escaped_quotes_do_not_open_a_call():
    assert top_level_calls('="He said ""FILTER("""') == []
    assert returns_array('="He said ""FILTER("""') is False


def test_py_formula_is_not_array_even_if_string_mentions_filter():
    formula = '=PY("result = data[data.flag]; FILTER leftover"; A1:B9)'
    assert top_level_calls(formula) == ["PY"]
    assert returns_array(formula) is False


def test_sheet_qualified_name_is_one_token():
    assert top_level_calls("=MOD.FUNC(A1)") == ["MOD.FUNC"]
    assert returns_array("=MOD.FUNC(A1)") is False


def test_forced_overrides_detection():
    assert returns_array("=A1+A2", forced=True) is True
    assert returns_array("=SORT(A1:A9)", forced=False) is False
    assert returns_array("not a formula", forced=True) is True
