# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Insert trusted vision helper HTML into Calc."""

from __future__ import annotations

from typing import Any

from plugin.calc.address_utils import index_to_column
from plugin.calc.rich_html import insert_cell_html_rich
from plugin.framework.errors import ToolExecutionError
from plugin.framework.i18n import _
from plugin.writer.images.image_tools import _get_selected_graphic_object


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


def insert_vision_html_into_calc(doc: Any, uno_ctx: Any, html: str) -> None:
    """Paste vision HTML into the cell below the selected graphic anchor."""
    col, row = calc_output_anchor_from_graphic(doc)
    # *row* is already one below the graphic anchor (see calc_output_anchor_from_graphic).
    cell_address = f"{index_to_column(col)}{row + 1}"
    insert_cell_html_rich(doc, uno_ctx, cell_address, html)
