# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for scripts/rename_identifier.py."""

from __future__ import annotations

from scripts.rename_identifier import rewrite_text


def test_rewrite_identifier_and_attr_prefix():
    src = 'import plugin.scripting.calc_functions as xl\nassert xl.sumif(a, b)\ns = "xl.countif("\n'
    out = rewrite_text(src, "xl", "calc")
    assert out is not None
    assert "as calc" in out
    assert "calc.sumif" in out
    assert '"calc.countif("' in out
    assert "as xl" not in out


def test_rewrite_skips_openpyxl_and_xlws_lines():
    src = "from openpyxl.styles import Font\n_xlws.PY(0,1)\nxl.sumif(x)\n"
    out = rewrite_text(src, "xl", "calc")
    assert out is not None
    assert "openpyxl.styles" in out
    assert "_xlws.PY" in out
    assert "calc.sumif" in out


def test_rewrite_noop():
    assert rewrite_text("np.sum(data)\n", "xl", "calc") is None
