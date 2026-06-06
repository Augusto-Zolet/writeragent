# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for vision result Calc sheet egress formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from plugin.calc.vision_egress import (
    calc_output_anchor_from_graphic,
    format_vision_for_calc,
    insert_vision_result_into_calc,
)
from plugin.framework.errors import ToolExecutionError


def test_format_vision_error_result():
    grid = format_vision_for_calc({"status": "error", "code": "PADDLEOCR_UNAVAILABLE", "message": "Install paddleocr"})
    assert grid[0][0].startswith("Vision error")
    assert "Install paddleocr" in grid[1][0]


def test_format_vision_success_with_lines():
    result = {
        "status": "ok",
        "helper": "extract_text",
        "full_text": "line1\nline2",
        "metrics": {"line_count": 2, "mean_confidence": 0.94},
        "warnings": [],
    }
    grid = format_vision_for_calc(result)
    flat = [cell for row in grid for cell in row if cell]
    assert any("extract_text" in str(cell) for cell in flat)
    assert any("line_count" in str(cell) for cell in flat)
    assert "line1" in flat
    assert "line2" in flat


def test_format_vision_empty_text():
    grid = format_vision_for_calc({"status": "ok", "helper": "extract_text", "full_text": "", "warnings": ["No text detected."]})
    flat = [cell for row in grid for cell in row if cell]
    assert any("extract_text" in str(cell) for cell in flat)
    assert any("No text detected." in str(cell) for cell in flat)


def test_format_vision_empty_text_without_warnings():
    grid = format_vision_for_calc({"status": "ok", "helper": "extract_text", "full_text": "", "warnings": []})
    flat = [cell for row in grid for cell in row if cell]
    assert any("(no text detected)" in str(cell) for cell in flat)


def test_format_extract_structure_with_tables():
    result = {
        "status": "ok",
        "helper": "extract_structure",
        "full_text": "Invoice",
        "blocks": [],
        "tables": [{"name": "table_1", "columns": ["Item", "Qty"], "rows": [["Widget", "2"]]}],
        "metrics": {"block_count": 1, "table_count": 1},
        "warnings": [],
    }
    grid = format_vision_for_calc(result)
    flat = [cell for row in grid for cell in row if cell]
    assert any("extract_structure" in str(cell) for cell in flat)
    assert any("table_count" in str(cell) for cell in flat)
    assert "Item" in flat
    assert "Widget" in flat


def test_format_extract_structure_empty():
    grid = format_vision_for_calc({"status": "ok", "helper": "extract_structure", "full_text": "", "tables": [], "blocks": [], "warnings": []})
    flat = [cell for row in grid for cell in row if cell]
    assert any("(no structure detected)" in str(cell) for cell in flat)


def test_calc_output_anchor_from_graphic_no_selection():
    doc = MagicMock()
    with patch("plugin.calc.vision_egress._get_selected_graphic_object", return_value=(None, None)):
        with pytest.raises(ToolExecutionError) as exc:
            calc_output_anchor_from_graphic(doc)
    assert exc.value.code == "NO_IMAGE_SELECTED"


def test_calc_output_anchor_from_graphic_no_anchor():
    doc = MagicMock()
    shape = MagicMock()
    shape.getPropertyValue.side_effect = Exception("no anchor")
    with patch("plugin.calc.vision_egress._get_selected_graphic_object", return_value=(shape, "calc")):
        with pytest.raises(ToolExecutionError) as exc:
            calc_output_anchor_from_graphic(doc)
    assert exc.value.code == "NO_OUTPUT_ANCHOR"


def test_calc_output_anchor_from_graphic_returns_row_below():
    doc = MagicMock()
    shape = MagicMock()
    anchor = MagicMock()
    addr = MagicMock()
    addr.Column = 2
    addr.Row = 4
    anchor.getCellAddress.return_value = addr
    shape.getPropertyValue.return_value = anchor
    with patch("plugin.calc.vision_egress._get_selected_graphic_object", return_value=(shape, "calc")):
        col, row = calc_output_anchor_from_graphic(doc)
    assert col == 2
    assert row == 5


@patch("plugin.calc.vision_egress.CellManipulator")
@patch("plugin.calc.vision_egress.CalcBridge")
def test_insert_vision_result_into_calc_writes_grid(mock_bridge, mock_manipulator):
    doc = MagicMock()
    ctx = MagicMock()
    write = MagicMock()
    mock_manipulator.return_value = write

    with patch("plugin.calc.vision_egress.calc_output_anchor_from_graphic", return_value=(1, 3)):
        row_count = insert_vision_result_into_calc(
            doc,
            ctx,
            {"status": "ok", "helper": "extract_text", "full_text": "hello", "warnings": []},
        )

    assert row_count > 0
    write.write_formula_range.assert_called_once()
    addr, grid = write.write_formula_range.call_args[0]
    assert addr == "B4"
    assert any("hello" in str(cell) for row in grid for cell in row)
