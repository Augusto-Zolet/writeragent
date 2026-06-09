# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""UNO tests for spreadsheet import preserve (live PY formulas)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from plugin.framework.uno_context import get_desktop
from plugin.testing_runner import native_test, setup, teardown

REPO_ROOT = Path(__file__).resolve().parents[2]
_GEN_PATH = REPO_ROOT / "scripts" / "generate_serialization_spreadsheet.py"

_test_doc = None
_test_ctx = None


@setup
def setup_preserve_uno(ctx):
    global _test_doc, _test_ctx
    _test_ctx = ctx
    import uno

    desktop = get_desktop(ctx)
    hidden = uno.createUnoStruct("com.sun.star.beans.PropertyValue", Name="Hidden", Value=True)
    _test_doc = desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, (hidden,))


@teardown
def teardown_preserve_uno(ctx):
    global _test_doc, _test_ctx
    if _test_doc:
        _test_doc.close(True)
    _test_doc = None
    _test_ctx = None


def _load_generator():
    if not _GEN_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("generate_serialization_spreadsheet", _GEN_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@native_test
def test_preserve_live_py_formulas_round_trip():
    from plugin.calc.address_utils import format_address
    from plugin.calc.spreadsheet_import.extract import py_formula_semantics
    from plugin.calc.spreadsheet_import.ingest import ingest_sheet
    from plugin.calc.spreadsheet_import.preserve import preserve_sheet_to_new_sheet

    sheet = _test_doc.getSheets().getByIndex(0)
    sheet.getCellByPosition(0, 0).setValue(10.0)
    sheet.getCellByPosition(0, 1).setValue(20.0)
    sheet.getCellByPosition(1, 0).setFormula("=SUM(A1:A2)")
    sheet.getCellByPosition(1, 1).setFormula('=PYTHON("np.sum(data)";A1:A2)')

    source_model = ingest_sheet(sheet)
    assert source_model.cells["B2"].type == "py_formula"

    output = preserve_sheet_to_new_sheet(_test_doc, sheet, target_name="PythonImport")
    target = _test_doc.getSheets().getByName("PythonImport")

    assert output.cells["A1"].value == 10.0
    assert output.cells["A2"].value == 20.0
    assert target.getCellByPosition(1, 0).getFormula() == "=SUM(A1:A2)"

    col, row = 1, 1
    src_formula = sheet.getCellByPosition(col, row).getFormula()
    tgt_formula = target.getCellByPosition(col, row).getFormula()
    assert py_formula_semantics(src_formula) == py_formula_semantics(tgt_formula)
    assert output.py_extracts and output.py_extracts[0].changed
    assert format_address(col, row) == "B2"
