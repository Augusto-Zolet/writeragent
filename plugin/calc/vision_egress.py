# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Format trusted vision helper results for multi-cell Calc sheet egress."""

from __future__ import annotations

from typing import Any

from plugin.calc.address_utils import index_to_column
from plugin.calc.bridge import CalcBridge
from plugin.calc.manipulator import CellManipulator
from plugin.calc.python_function import to_calc_compatible
from plugin.framework.errors import ToolExecutionError
from plugin.framework.i18n import _
from plugin.writer.images.image_tools import _get_selected_graphic_object


def _cell(value: Any) -> Any:
    return to_calc_compatible(value)


def _append_blank(rows: list[list[Any]]) -> None:
    if rows and rows[-1]:
        rows.append([])


def _append_key_value_block(rows: list[list[Any]], title: str, mapping: dict[str, Any]) -> None:
    if not mapping:
        return
    _append_blank(rows)
    rows.append([title])
    rows.append(["Key", "Value"])
    for key, val in mapping.items():
        if isinstance(val, (dict, list)):
            rows.append([str(key), str(val)])
        else:
            rows.append([str(key), _cell(val)])


def calc_output_anchor_from_graphic(doc: Any) -> tuple[int, int]:
    """Return (start_col, start_row) one row below the selected graphic's anchor cell."""
    obj, _doc_type = _get_selected_graphic_object(doc)
    if obj is None:
        raise ToolExecutionError(
            _("Select an embedded image, then Run again."),
            code="NO_IMAGE_SELECTED",
        )

    anchor = None
    try:
        if hasattr(obj, "getPropertyValue"):
            anchor = obj.getPropertyValue("Anchor")
    except Exception:
        anchor = None

    if anchor is None:
        raise ToolExecutionError(
            _("Anchor the image to a cell, select it, then Run again."),
            code="NO_OUTPUT_ANCHOR",
        )

    try:
        addr = anchor.getCellAddress()
        col = int(addr.Column)
        row = int(addr.Row)
    except Exception:
        raise ToolExecutionError(
            _("Anchor the image to a cell, select it, then Run again."),
            code="NO_OUTPUT_ANCHOR",
        ) from None

    return col, row + 1


def format_vision_for_calc(result: dict[str, Any]) -> list[list[Any]]:
    """Turn a vision helper result dict into a row-major grid for ``write_formula_range``."""
    rows: list[list[Any]] = []

    if result.get("status") == "error":
        code = str(result.get("code") or "ERROR")
        message = str(result.get("message") or "Vision helper failed.")
        return [[f"Vision error ({code})"], [message]]

    helper = str(result.get("helper") or "vision")
    rows.append([helper])

    metrics = result.get("metrics")
    if isinstance(metrics, dict) and metrics:
        subset = {k: metrics[k] for k in ("line_count", "mean_confidence") if k in metrics}
        if subset:
            _append_key_value_block(rows, "Metrics", subset)

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        _append_blank(rows)
        rows.append(["Warnings"])
        for item in warnings:
            rows.append([str(item)])

    full_text = str(result.get("full_text") or "")
    if full_text:
        _append_blank(rows)
        rows.append(["Text"])
        for line in full_text.splitlines():
            rows.append([line])
    elif len(rows) == 1:
        rows.append(["(no text detected)"])

    return rows


def insert_vision_result_into_calc(
    doc: Any,
    uno_ctx: Any,
    result: dict[str, Any],
    *,
    start_col: int | None = None,
    start_row: int | None = None,
) -> int:
    """Write formatted vision output starting at the graphic anchor (or explicit coords). Returns row count."""
    del uno_ctx  # CalcBridge uses doc only; kept for parity with analysis egress.
    if start_col is None or start_row is None:
        col, row = calc_output_anchor_from_graphic(doc)
        start_col = col if start_col is None else start_col
        start_row = row if start_row is None else start_row

    grid = format_vision_for_calc(result)
    bridge = CalcBridge(doc)
    manipulator = CellManipulator(bridge)
    addr = f"{index_to_column(start_col)}{start_row + 1}"
    manipulator.write_formula_range(addr, grid)
    return len(grid)
