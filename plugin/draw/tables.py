# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Table tools for Draw/Impress slides (drawing table shapes, not Writer text tables)."""

from plugin.draw.base import ToolDrawTableBase


def _table_model(shape):
    if hasattr(shape, "Model"):
        model = shape.Model
        if model is not None:
            return model
    if hasattr(shape, "Table"):
        return shape.Table
    try:
        return shape.getModel()
    except Exception:
        return None


def fill_table_cells(table, data) -> int:
    """Write a 2D string grid into ``table.getCellByPosition(col, row)``. Returns cells written."""
    written = 0
    for r_idx, row in enumerate(data):
        if not isinstance(row, (list, tuple)):
            continue
        for c_idx, val in enumerate(row):
            cell = table.getCellByPosition(c_idx, r_idx)
            text = "" if val is None else str(val)
            if hasattr(cell, "getText"):
                cell.getText().setString(text)
            elif hasattr(cell, "setString"):
                cell.setString(text)
            written += 1
    return written


class InsertTable(ToolDrawTableBase):
    name = "insert_table"
    intent = "edit"
    description = (
        "Insert a table on a Draw/Impress page. Position/size are 1/100 mm. "
        "Optional data is a 2D array of cell strings [[row0col0, row0col1], ...]."
    )
    parameters = {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "0-based page index (active page if omitted)"},
            "rows": {"type": "integer", "description": "Number of rows"},
            "columns": {"type": "integer", "description": "Number of columns"},
            "x": {"type": "integer", "description": "X position in 1/100 mm (default: 3000)"},
            "y": {"type": "integer", "description": "Y position in 1/100 mm (default: 4000)"},
            "width": {"type": "integer", "description": "Table width in 1/100 mm (default: 20000)"},
            "height": {"type": "integer", "description": "Table height in 1/100 mm (default: 10000)"},
            "data": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "2D cell strings",
            },
        },
        "required": ["rows", "columns"],
    }
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from com.sun.star.awt import Point, Size
        from plugin.draw.bridge import DrawBridge

        rows = kwargs.get("rows")
        columns = kwargs.get("columns")
        if rows is None or columns is None:
            return self._tool_error("rows and columns are required.")
        rows = int(rows)
        columns = int(columns)
        if rows < 1 or columns < 1:
            return self._tool_error("rows and columns must be at least 1.")

        bridge = DrawBridge(ctx.doc)
        idx = kwargs.get("page")
        actual_idx = idx if idx is not None else ctx.active_page_index
        if actual_idx is None:
            actual_idx = bridge.get_active_page_index()
        try:
            page = bridge.get_pages().getByIndex(actual_idx)
        except Exception:
            return self._tool_error("Invalid page index: %s" % actual_idx)
        if page is None:
            return self._tool_error("No draw page available.")

        from plugin.draw.layout import coerce_int

        x = coerce_int(kwargs.get("x"), 3000)
        y = coerce_int(kwargs.get("y"), 4000)
        width = coerce_int(kwargs.get("width"), 20000)
        height = coerce_int(kwargs.get("height"), 10000)

        try:
            shape = ctx.doc.createInstance("com.sun.star.drawing.TableShape")
            for name, val in (("Rows", rows), ("Columns", columns)):
                try:
                    shape.setPropertyValue(name, val)
                except Exception:
                    pass
            page.add(shape)
            shape.setSize(Size(width, height))
            shape.setPosition(Point(x, y))
        except Exception as exc:
            return self._tool_error("Failed to create table: %s" % exc)

        written = 0
        data = kwargs.get("data")
        if data:
            table = _table_model(shape)
            if table is None:
                return {
                    "status": "ok",
                    "message": "Table inserted but cell model was unavailable; data not filled",
                    "page": actual_idx,
                    "index": page.getCount() - 1,
                    "warning": "table_model_unavailable",
                }
            try:
                written = fill_table_cells(table, data)
            except Exception as exc:
                return self._tool_error("Failed to fill table cells: %s" % exc)

        return {
            "status": "ok",
            "message": "Table inserted",
            "page": actual_idx,
            "index": page.getCount() - 1,
            "rows": rows,
            "columns": columns,
            "cells_written": written,
        }
