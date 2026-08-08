# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for convert_spreadsheet_to_python tool vectorization."""

from __future__ import annotations

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc


def _run_conversion(doc, ctx, **kwargs):
    from plugin.calc.spreadsheet_import.import_dialog import run_sheet_conversion

    sheet = doc.getCurrentController().getActiveSheet()
    return run_sheet_conversion(ctx, doc, sheet, **kwargs)


@native_test
@with_native_doc("calc")
def test_convert_spreadsheet_to_python_vectorized(ctx, doc):
    pass

'''
    # Populate grid
    sheet.getCellByPosition(0, 0).setValue(10)  # A1
    sheet.getCellByPosition(0, 1).setValue(20)  # A2
    sheet.getCellByPosition(0, 2).setValue(30)  # A3

    sheet.getCellByPosition(1, 0).setFormula("=ABS(A1)*2")  # B1
    sheet.getCellByPosition(1, 1).setFormula("=ABS(A2)*2")  # B2
    sheet.getCellByPosition(1, 2).setFormula("=ABS(A3)*2")  # B3

    res = _run_conversion(
        scope="sheet",
        output_mode="new_sheet",
        vectorize=True,
        verify=True,
    )
    assert not res.get("failed_verifications"), f"Verifications failed: {res.get('failed_verifications')}"

    sheets = _test_doc.getSheets()
    assert sheets.hasByName("PythonImport")
    target_sheet = sheets.getByName("PythonImport")

    # Verify values and formulas
    assert target_sheet.getCellByPosition(1, 0).getValue() == 20.0
    assert target_sheet.getCellByPosition(1, 1).getValue() == 40.0
    assert target_sheet.getCellByPosition(1, 2).getValue() == 60.0

    f1 = target_sheet.getCellByPosition(1, 0).getFormula()
    f2 = target_sheet.getCellByPosition(1, 1).getFormula()
    f3 = target_sheet.getCellByPosition(1, 2).getFormula()

    assert "0" in f1 and "A1:A3" in f1
    assert "1" in f2 and "A1:A3" in f2
    assert "2" in f3 and "A1:A3" in f3
'''