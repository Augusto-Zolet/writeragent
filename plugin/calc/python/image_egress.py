# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Insert matplotlib image payloads on Calc sheets (=PYTHON / chat tool)."""

from __future__ import annotations

import logging
import os
from typing import Any

from plugin.scripting.payload_codec import write_image_payload_to_temp

log = logging.getLogger(__name__)


# Default chart overlay size for unmerged single cells: 10 cm x 6 cm (10000 x 6000 in 1/100 mm).
# Design decision: When a user merges a block of cells (e.g. B2:H18) as a chart placeholder,
# we fit the shape to that merged area (ResizeWithCell=True). For an ordinary 1x1 cell,
# setting shape size to cell_size would crush the chart to a tiny ~22mm x 4.5mm sliver;
# instead we use DEFAULT_CHART_SIZE and keep ResizeWithCell=False.
DEFAULT_CHART_SIZE_WIDTH = 10000
DEFAULT_CHART_SIZE_HEIGHT = 6000


def insert_image_result_on_sheet(ctx: Any, payload: dict[str, Any]) -> None:
    """Write image payload bytes to a temp file and insert as a cell-anchored shape on the active sheet."""
    import uno
    from com.sun.star.awt import Size

    tmp_path = write_image_payload_to_temp(payload)
    file_url = uno.systemPathToFileUrl(os.path.abspath(tmp_path))
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.getCurrentComponent()
    ctrl = doc.getCurrentController()
    sheet = ctrl.getActiveSheet()
    draw_page = sheet.DrawPage

    shape = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
    default_size = Size(DEFAULT_CHART_SIZE_WIDTH, DEFAULT_CHART_SIZE_HEIGHT)
    shape.setSize(default_size)
    draw_page.add(shape)
    shape.setPropertyValue("GraphicURL", file_url)

    # Anchor the image to the active cell so it moves with the grid.
    try:
        from plugin.calc.calc_utils import get_cell_geometry

        selection = ctrl.getSelection()
        if selection is not None:
            addr = selection.getRangeAddress()
            cell = sheet.getCellByPosition(addr.StartColumn, addr.StartRow)
            # Bugfix: Previously shape.setSize(cell_size) was called unconditionally, which
            # crushed charts down to the ~22mm x 4.5mm size of a single cell.
            # Now: Only size to cell_size if the cell is merged (or selection is a multi-cell range).
            cell_pos, cell_size = get_cell_geometry(sheet, cell)
            is_merged = bool(getattr(cell, "IsMerged", False))
            is_multi_cell = bool(addr.EndColumn > addr.StartColumn or addr.EndRow > addr.StartRow)

            shape.setPropertyValue("Anchor", cell)
            if hasattr(shape, "setPosition"):
                shape.setPosition(cell_pos)

            if is_merged or is_multi_cell:
                shape.setPropertyValue("ResizeWithCell", True)
                if hasattr(shape, "setSize"):
                    shape.setSize(cell_size)
            else:
                shape.setPropertyValue("ResizeWithCell", False)
                if hasattr(shape, "setSize"):
                    shape.setSize(default_size)
    except Exception:
        log.debug("insert_image_result_on_sheet: could not anchor to cell", exc_info=True)
