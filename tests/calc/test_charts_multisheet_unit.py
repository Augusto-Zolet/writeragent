# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
"""Unit tests for Calc multi-sheet chart helpers and non-empty exception formatting (no UNO required)."""

from unittest.mock import MagicMock
from plugin.calc.charts import (
    _format_chart_exception_msg,
    _get_all_calc_chart_names,
    _find_calc_chart_and_sheet,
)


def test_format_chart_exception_msg():
    # 1. Standard python exception with text
    e1 = ValueError("invalid value")
    assert _format_chart_exception_msg(e1) == "ValueError: invalid value"

    # 2. Exception with empty str() but Message attribute (UNO Exception style)
    class DummyUnoException(Exception):
        def __init__(self, message):
            self.Message = message
        def __str__(self):
            return ""

    e2 = DummyUnoException("ElementExistException: Name exists")
    assert _format_chart_exception_msg(e2) == "DummyUnoException: ElementExistException: Name exists"

    # 3. Exception with completely empty message
    class BlankException(Exception):
        def __str__(self):
            return ""

    e3 = BlankException()
    assert _format_chart_exception_msg(e3) == "BlankException"


def test_is_chart_name_used_and_count():
    doc = MagicMock()

    sheet1 = MagicMock()
    sheet1.getName.return_value = "Sheet1"
    charts1 = MagicMock()
    charts1.hasByName.side_effect = lambda name: name == "Chart_0"
    charts1.getElementNames.return_value = ["Chart_0"]
    sheet1.getCharts.return_value = charts1

    sheet2 = MagicMock()
    sheet2.getName.return_value = "Sheet2"
    charts2 = MagicMock()
    charts2.hasByName.side_effect = lambda name: name == "Chart_1"
    charts2.getElementNames.return_value = ["Chart_1"]
    sheet2.getCharts.return_value = charts2

    sheets = MagicMock()
    sheets.getElementNames.return_value = ["Sheet1", "Dashboard"]
    sheets.getByName.side_effect = lambda name: sheet1 if name == "Sheet1" else sheet2
    doc.getSheets.return_value = sheets

    # Chart_0 is on Sheet1, Chart_1 is on Sheet2
    all_names = _get_all_calc_chart_names(doc)
    assert "Chart_0" in all_names
    assert "Chart_1" in all_names
    assert "Chart_2" not in all_names

    # Find chart and sheet
    chart_obj, found_sheet = _find_calc_chart_and_sheet(doc, "Chart_1")
    assert found_sheet is sheet2
    assert chart_obj is not None

    chart_obj_none, sheet_none = _find_calc_chart_and_sheet(doc, "Chart_999")
    assert chart_obj_none is None
    assert sheet_none is None
