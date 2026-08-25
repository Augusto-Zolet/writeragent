# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Collabora pythoncompute OriginalName → LibrePy =PY() prefix rewrite."""

from __future__ import annotations

from plugin.calc.python.cell_discovery import canonicalize_py_formula_for_parse, is_py_formula_text
from plugin.calc.python.collabora_formula import (
    is_collabora_py_formula,
    rewrite_collabora_addin_prefix,
)
from plugin.calc.python.formula_edit import parse_python_formula


_GETPY = '=ORG.COLLABORAOFFICE.SHEET.ADDIN.PYTHONCOMPUTEFUNCTIONS.GETPY("result = 1"; A1:A2)'
_GETPYTHON = '=ORG.COLLABORAOFFICE.SHEET.ADDIN.PYTHONCOMPUTEFUNCTIONS.GETPYTHON("result = 2")'


def test_rewrite_getpy_to_py():
    out = rewrite_collabora_addin_prefix(_GETPY)
    assert out.startswith("=PY(")
    assert 'result = 1' in out
    assert "A1:A2" in out
    assert "COLLABORAOFFICE" not in out.upper()


def test_rewrite_getpython_to_python():
    out = rewrite_collabora_addin_prefix(_GETPYTHON)
    assert out.startswith("=PYTHON(")
    assert "result = 2" in out


def test_rewrite_is_case_insensitive():
    raw = '=org.collaboraoffice.sheet.addin.PythonComputeFunctions.getPy("x")'
    assert rewrite_collabora_addin_prefix(raw).startswith("=PY(")


def test_rewrite_preserves_space_after_equals():
    raw = '= ORG.COLLABORAOFFICE.SHEET.ADDIN.PYTHONCOMPUTEFUNCTIONS.GETPY("x")'
    assert rewrite_collabora_addin_prefix(raw).startswith("= PY(")


def test_rewrite_leaves_writeragent_and_short_py_alone():
    wa = '=ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION.PY("result = 1")'
    assert rewrite_collabora_addin_prefix(wa) == wa
    short = '=PY("result = 1")'
    assert rewrite_collabora_addin_prefix(short) == short
    assert rewrite_collabora_addin_prefix("=SUM(A1:A2)") == "=SUM(A1:A2)"


def test_is_collabora_py_formula():
    assert is_collabora_py_formula(_GETPY)
    assert is_collabora_py_formula(_GETPYTHON)
    assert not is_collabora_py_formula('=PY("result = 1")')
    assert not is_collabora_py_formula('=ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION.PY("x")')


def test_canonicalize_and_parse_collabora_getpy():
    canonical = canonicalize_py_formula_for_parse(_GETPY)
    assert canonical.upper().startswith("=PY(")
    assert is_py_formula_text(_GETPY)
    parts = parse_python_formula(canonical)
    assert parts is not None
    assert parts.code == "result = 1"


def test_maybe_rewrite_skips_non_calc():
    from plugin.calc.python.collabora_formula import maybe_rewrite_collabora_py_formulas

    class _Writer:
        def supportsService(self, name: str) -> bool:
            return name != "com.sun.star.sheet.SpreadsheetDocument"

    assert maybe_rewrite_collabora_py_formulas(_Writer()) == 0
    assert maybe_rewrite_collabora_py_formulas(None) == 0
