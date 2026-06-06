# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Format trusted vision helper results for Writer document egress."""

from __future__ import annotations

from typing import Any

from plugin.framework.errors import ToolExecutionError


def is_vision_result(value: Any) -> bool:
    """True when *value* matches the compact vision helper result contract."""
    if not isinstance(value, dict):
        return False
    if "status" not in value:
        return False
    return bool(value.get("helper")) or value.get("status") == "error"


def format_vision_structure_for_writer(result: dict[str, Any]) -> str:
    """Return structure text for Writer insert — full_text, first table TSV, or block text."""
    if result.get("status") == "error":
        code = str(result.get("code") or "VISION_ERROR")
        message = str(result.get("message") or "Vision helper failed.")
        raise ToolExecutionError(message, code=code, details={"vision_result": result})

    if result.get("status") != "ok":
        raise ToolExecutionError(
            "Vision helper returned an unexpected status.",
            code="VISION_ERROR",
            details={"vision_result": result},
        )

    full_text = str(result.get("full_text") or "").strip()
    if full_text:
        return full_text

    tables = result.get("tables")
    if isinstance(tables, list) and tables:
        table = tables[0]
        if isinstance(table, dict):
            columns = table.get("columns")
            table_rows = table.get("rows")
            lines: list[str] = []
            if isinstance(columns, list) and columns:
                lines.append("\t".join(str(c) for c in columns))
            if isinstance(table_rows, list):
                for row in table_rows:
                    if isinstance(row, list):
                        lines.append("\t".join(str(c) for c in row))
            if lines:
                return "\n".join(lines)

    blocks = result.get("blocks")
    if isinstance(blocks, list):
        block_texts = [str(b.get("text") or "").strip() for b in blocks if isinstance(b, dict)]
        block_texts = [t for t in block_texts if t]
        if block_texts:
            return "\n".join(block_texts)

    return ""


def format_vision_for_writer(result: dict[str, Any]) -> str:
    """Return plain OCR text for insertion at the Writer text cursor."""
    helper = str(result.get("helper") or "")
    if helper == "extract_structure":
        return format_vision_structure_for_writer(result)

    if result.get("status") == "error":
        code = str(result.get("code") or "VISION_ERROR")
        message = str(result.get("message") or "Vision helper failed.")
        raise ToolExecutionError(message, code=code, details={"vision_result": result})

    if result.get("status") != "ok":
        raise ToolExecutionError(
            "Vision helper returned an unexpected status.",
            code="VISION_ERROR",
            details={"vision_result": result},
        )

    full_text = result.get("full_text")
    if full_text is None:
        raise ToolExecutionError(
            "Vision helper result is missing full_text.",
            code="VISION_ERROR",
            details={"vision_result": result},
        )
    return str(full_text)
