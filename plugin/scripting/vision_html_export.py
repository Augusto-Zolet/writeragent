# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export Docling / Paddle vision OCR results to HTML for LO import."""

from __future__ import annotations

import html as html_module
import importlib
import logging
from typing import Any

log = logging.getLogger(__name__)


def export_docling_to_html(document: Any, params: dict[str, Any]) -> str:
    """Return rich HTML from a DoclingDocument (bold, tables, headings)."""
    docling_doc_mod = importlib.import_module("docling_core.types.doc")
    image_ref_mode = docling_doc_mod.ImageRefMode

    html_style = str(params.get("html_style") or "single_column").strip().lower()
    if html_style == "split_page":
        try:
            from docling_core.transforms.serializer.html import (
                HTMLDocSerializer,
                HTMLOutputStyle,
                HTMLParams,
            )

            ser = HTMLDocSerializer(
                doc=document,
                params=HTMLParams(
                    image_mode=image_ref_mode.EMBEDDED,
                    output_style=HTMLOutputStyle.SPLIT_PAGE,
                ),
            )
            return str(ser.serialize().text or "")
        except Exception:
            log.debug("Docling split_page HTML export failed; falling back to export_to_html", exc_info=True)

    if hasattr(document, "export_to_html"):
        return str(document.export_to_html(image_mode=image_ref_mode.EMBEDDED) or "")
    return ""


def html_from_paddle_regions(regions: list[dict[str, Any]]) -> str:
    """Minimal HTML from Paddle OCR line regions (reading order)."""
    parts: list[str] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        text = str(region.get("text") or "").strip()
        if text:
            parts.append(f"<p>{html_module.escape(text)}</p>")
    return "\n".join(parts) if parts else ""


def _paddle_block_tag(block_type: str) -> str:
    label = block_type.strip().lower()
    if label in ("title", "section_header", "header", "heading"):
        return "h2"
    if label in ("caption", "footnote"):
        return "p"
    return "p"


def _html_table_from_columns_rows(columns: list[Any], rows: list[list[Any]]) -> str:
    if not columns and not rows:
        return ""
    lines = ["<table border=\"1\">"]
    if columns:
        lines.append("<thead><tr>")
        for col in columns:
            lines.append(f"<th>{html_module.escape(str(col))}</th>")
        lines.append("</tr></thead>")
    if rows:
        lines.append("<tbody>")
        for row in rows:
            if not isinstance(row, list):
                continue
            lines.append("<tr>")
            for cell in row:
                lines.append(f"<td>{html_module.escape(str(cell))}</td>")
            lines.append("</tr>")
        lines.append("</tbody>")
    lines.append("</table>")
    return "".join(lines)


def html_from_paddle_structure(
    blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> str:
    """Build HTML from Paddle PP-Structure blocks and parsed tables."""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "text")
        text = str(block.get("text") or "").strip()
        if block_type == "table" and not text:
            continue
        tag = _paddle_block_tag(block_type)
        if not text:
            continue
        if tag == "h2":
            parts.append(f"<h2>{html_module.escape(text)}</h2>")
        else:
            parts.append(f"<p>{html_module.escape(text)}</p>")

    for table in tables:
        if not isinstance(table, dict):
            continue
        table_html = _html_table_from_columns_rows(
            list(table.get("columns") or []),
            [list(r) for r in (table.get("rows") or []) if isinstance(r, list)],
        )
        if table_html:
            parts.append(table_html)

    return "\n".join(parts) if parts else ""
