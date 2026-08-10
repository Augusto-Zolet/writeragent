# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for CalcBridge sheet-qualified range resolution."""

from unittest.mock import MagicMock

from plugin.calc.bridge import CalcBridge


def _sheet(name: str) -> MagicMock:
    sheet = MagicMock()
    sheet.getName.return_value = name
    return sheet


def test_resolve_prefix_wins_over_sheet_name():
    doc = MagicMock()
    summary = _sheet("Summary")
    other = _sheet("Other")
    sheets = MagicMock()
    sheets.hasByName.side_effect = lambda n: n in ("Summary", "Other")
    sheets.getByName.side_effect = lambda n: summary if n == "Summary" else other
    sheets.getElementNames.return_value = ("Summary", "Other")
    doc.getSheets.return_value = sheets

    bridge = CalcBridge(doc)
    sheet, address = bridge.resolve("Summary.D4:D6", sheet_name=None)
    assert sheet is summary
    assert address == "D4:D6"


def test_resolve_conflict_raises():
    doc = MagicMock()
    bridge = CalcBridge(doc)
    try:
        bridge.resolve("Summary.A1", sheet_name="Other")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Summary" in str(e)
        assert "Other" in str(e)


def test_get_cell_range_honours_sheet_prefix():
    doc = MagicMock()
    data = _sheet("Data")
    active = _sheet("Active")
    sheets = MagicMock()
    sheets.hasByName.side_effect = lambda n: n == "Data"
    sheets.getByName.return_value = data
    sheets.getElementNames.return_value = ("Data", "Active")
    doc.getSheets.return_value = sheets

    bridge = CalcBridge(doc)
    bridge.get_cell_range(active, "Data.A1:B2")
    data.getCellRangeByPosition.assert_called_once_with(0, 0, 1, 1)
    active.getCellRangeByPosition.assert_not_called()
