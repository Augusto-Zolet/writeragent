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
    """Write image payload bytes to a temp file and insert as a cell-anchored shape on the active sheet.

    Marshals execution to the main VCL UI thread if invoked from a background worker thread.
    """
    from plugin.framework.queue_executor import execute_on_main_thread
    from plugin.framework.thread_guard import on_main_thread

    # Thread safety invariant: Drawing layer manipulation (DrawPage, GraphicObjectShape, cell geometry)
    # must run on LibreOffice's main VCL thread to prevent internal C++ state corruption and deadlocks.
    # If called from a background recalculation or script worker thread, marshal via execute_on_main_thread.
    if not on_main_thread():
        execute_on_main_thread(_insert_image_result_on_sheet_impl, ctx, payload)
        return

    _insert_image_result_on_sheet_impl(ctx, payload)


def _insert_image_result_on_sheet_impl(ctx: Any, payload: dict[str, Any]) -> None:
    """Main-thread implementation of graphic shape creation and anchoring."""
    import uno
    from com.sun.star.awt import Size

    # Bugfix: Previously, insert_image_result_on_sheet did `desktop.getCurrentComponent().getCurrentController()`
    # directly. During document load or background recalc, getCurrentComponent() or getCurrentController() can
    # return None, causing `AttributeError: 'NoneType' object has no attribute 'getCurrentController'`.
    # Fix: Resolve the document model via `get_calc_document_from_ctx(ctx)` with null checks on doc,
    # controller, and active sheet before attempting shape creation.
    try:
        from plugin.scripting.document_scripts import get_calc_document_from_ctx

        doc = get_calc_document_from_ctx(ctx)
        if doc is None:
            log.debug("insert_image_result_on_sheet: no active Calc document resolved from context")
            return

        ctrl = doc.getCurrentController() if hasattr(doc, "getCurrentController") else None
        if ctrl is not None and hasattr(ctrl, "getActiveSheet") and ctrl.getActiveSheet():
            sheet = ctrl.getActiveSheet()
        elif hasattr(doc, "getSheets") and doc.getSheets().getCount() > 0:
            sheet = doc.getSheets().getByIndex(0)
        else:
            log.debug("insert_image_result_on_sheet: could not resolve active sheet")
            return

        draw_page = getattr(sheet, "DrawPage", None)
        if draw_page is None:
            log.debug("insert_image_result_on_sheet: active sheet has no DrawPage")
            return

        tmp_path = write_image_payload_to_temp(payload)
        file_url = uno.systemPathToFileUrl(os.path.abspath(tmp_path))

        shape = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
        default_size = Size(DEFAULT_CHART_SIZE_WIDTH, DEFAULT_CHART_SIZE_HEIGHT)
        shape.setSize(default_size)
        draw_page.add(shape)
        shape.setPropertyValue("GraphicURL", file_url)

        # Anchor the image to the active cell so it moves with the grid.
        if ctrl is not None and hasattr(ctrl, "getSelection"):
            try:
                from plugin.calc.calc_utils import get_cell_geometry

                selection = ctrl.getSelection()
                if selection is not None and hasattr(selection, "getRangeAddress"):
                    addr = selection.getRangeAddress()
                    cell = sheet.getCellByPosition(addr.StartColumn, addr.StartRow)
                    cell_pos, cell_size = get_cell_geometry(sheet, cell)
                    is_merged = bool(getattr(cell, "IsMerged", False))
                    is_multi_cell = bool(addr.EndColumn > addr.StartColumn or addr.EndRow > addr.StartRow)

                    shape.setPropertyValue("Anchor", cell)
                    if hasattr(shape, "setPosition"):
                        shape.setPosition(cell_pos)

                    if is_merged or is_multi_cell:
                        shape.setPropertyValue("ResizeWithCell", True)
                        if hasattr(shape, "setSize"):
                            # Note for future enhancement: If a merged block has very thin row heights
                            # (e.g. < 40mm / 4000 1/100mm), a minimum dimension clamp could be applied here:
                            #   effective_height = max(cell_size.Height, MIN_CHART_SIZE_HEIGHT)
                            #   effective_width = max(cell_size.Width, MIN_CHART_SIZE_WIDTH)
                            #   shape.setSize(Size(effective_width, effective_height))
                            # For now, we scale directly to the full merged area defined on the sheet.
                            shape.setSize(cell_size)
                    else:
                        shape.setPropertyValue("ResizeWithCell", False)
                        if hasattr(shape, "setSize"):
                            shape.setSize(default_size)
            except Exception:
                log.debug("insert_image_result_on_sheet: could not anchor to cell", exc_info=True)
    except Exception:
        log.exception("insert_image_result_on_sheet failed to insert graphic shape")
