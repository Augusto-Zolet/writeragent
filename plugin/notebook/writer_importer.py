# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Import a Jupyter .ipynb into Writer: body text for display, form fields for editable code."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from com.sun.star.awt import Point, Size

from plugin.contrib.nbformat import read_ipynb
from plugin.writer.specialized.forms import _get_form_draw_page

log = logging.getLogger("writeragent.notebook")

# 1/100 mm — draw-page code field width
_DEFAULT_WIDTH = 14000
_MIN_FIELD_HEIGHT = 600
_LINE_HEIGHT = 380
_MAX_FIELD_HEIGHT = 20000
_STACK_MARGIN_X = 5000
_STACK_GAP = 400
_STACK_INITIAL_BOTTOM = 800
_PROGRESS_EVERY_N_CELLS = 10
_SLOW_ADD_MS = 2000
_MAX_IMPORT_TEXT_CHARS = 50_000
_TRUNCATION_SUFFIX = "\n\n[… truncated for import …]"
_MAX_OUTPUTS_PER_CELL = 200

# Writer paragraph styles (document locale usually provides these English names).
_STYLE_CELL_HEADING = "Heading 2"
_STYLE_SECTION_HEADING = "Heading 3"
_STYLE_OUTPUT = "Preformatted Text"
_STYLE_BODY = "Text Body"

# PNG / GraphicObject import: full implementation kept in ''' ... ''' below (disabled for perf).
_PARAGRAPH_BREAK = 0  # com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK


def _mono_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


class _ImportStackCursor:
    """O(1) vertical stacking for code-cell form controls on the draw page."""

    __slots__ = ("_margin_x", "_gap", "_max_bottom", "shape_count")

    def __init__(self, dp: Any) -> None:
        self._margin_x = _STACK_MARGIN_X
        self._gap = _STACK_GAP
        self._max_bottom = _STACK_INITIAL_BOTTOM
        self.shape_count = 0
        self._seed_from_draw_page(dp)

    def _seed_from_draw_page(self, dp: Any) -> None:
        try:
            count = dp.getCount()
        except Exception:
            log.debug("draw page getCount failed during stack seed", exc_info=True)
            return
        for i in range(count):
            try:
                s = dp.getByIndex(i)
                pos = s.getPosition()
                sz = s.getSize()
                self._max_bottom = max(self._max_bottom, pos.Y + sz.Height)
                self.shape_count += 1
            except Exception:
                continue

    def place(self, height: int) -> Point:
        y = self._max_bottom + self._gap
        self._max_bottom = y + height
        self.shape_count += 1
        return Point(self._margin_x, y)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _coerce_notebook_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(line) for line in value)
    return str(value)


def _height_for_text(text: str) -> int:
    lines = max(1, (text or "").count("\n") + 1)
    return min(_MAX_FIELD_HEIGHT, max(_MIN_FIELD_HEIGHT, lines * _LINE_HEIGHT))


def _prepare_display_text(text: str) -> tuple[str, bool]:
    display = text or ""
    if len(display) <= _MAX_IMPORT_TEXT_CHARS:
        return display, False
    keep = max(0, _MAX_IMPORT_TEXT_CHARS - len(_TRUNCATION_SUFFIX))
    return display[:keep] + _TRUNCATION_SUFFIX, True


def _mime_plain(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data) if data is not None else ""
    if "text/plain" in data:
        plain = data["text/plain"]
        return plain if isinstance(plain, str) else "".join(plain)
    for key in sorted(data.keys()):
        if key.startswith("text/"):
            val = data[key]
            return val if isinstance(val, str) else "".join(val)
    return ""


def format_output_text(output: Any) -> str:
    """Turn one nbformat output object into plain text for the document body."""
    output_type = getattr(output, "output_type", None) or output.get("output_type", "")
    if output_type == "stream":
        name = getattr(output, "name", None) or output.get("name", "stdout")
        text = _coerce_notebook_text(getattr(output, "text", None) or output.get("text", ""))
        return f"[{name}]\n{text}"
    if output_type == "error":
        tb = getattr(output, "traceback", None) or output.get("traceback", "")
        if isinstance(tb, list):
            tb = "\n".join(tb)
        return _strip_ansi(str(tb))
    if output_type in ("execute_result", "display_data"):
        data = getattr(output, "data", None) or output.get("data", {})
        if isinstance(data, dict):
            if "image/png" in data or "image/jpeg" in data:
                '''
                return "[image/png output — see graphic on draw page if inserted]"
                '''
                return "[image output omitted during import]"
            plain = _mime_plain(data)
            if plain:
                return plain
            mime_types = ", ".join(sorted(data.keys()))
            return f"[non-text output: {mime_types}]"
    return str(output)


def format_all_outputs(outputs: list[Any]) -> str:
    parts = [format_output_text(o) for o in (outputs or [])]
    return "\n\n".join(p for p in parts if p.strip())


def _format_outputs_for_body(outputs: list[Any], cell_index: int) -> str:
    out_list = outputs or []
    if len(out_list) > _MAX_OUTPUTS_PER_CELL:
        log.warning(
            "notebook import cell=%d truncating outputs %d -> %d",
            cell_index,
            len(out_list),
            _MAX_OUTPUTS_PER_CELL,
        )
        out_list = out_list[:_MAX_OUTPUTS_PER_CELL]
    parts: list[str] = []
    for output in out_list:
        text = format_output_text(output)
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts)


'''
# --- PNG output import (draw-page GraphicObject) — uncomment this block to re-enable ---
import base64
import tempfile

import uno

_MAX_PNG_DECODE_BYTES = 8 * 1024 * 1024
_PNG_SHAPE_HEIGHT = 8000


def _try_insert_png_on_draw_page(doc: Any, dp: Any, stack: _ImportStackCursor, b64_data: str) -> bool:
    """Decode base64 PNG and place a graphic shape on the draw page."""
    shapes_before = stack.shape_count
    b64_data = _coerce_notebook_text(b64_data)
    png_bytes = len(b64_data)
    if png_bytes > _MAX_PNG_DECODE_BYTES:
        log.warning(
            "notebook import skip PNG decode size=%d max=%d",
            png_bytes,
            _MAX_PNG_DECODE_BYTES,
        )
        return False
    try:
        raw = base64.b64decode(b64_data, validate=False)
    except Exception:
        log.debug("PNG base64 decode failed", exc_info=True)
        _log_shape_add(step="png", shapes_before=shapes_before, create_ms=0, add_ms=0, ok=False, png_bytes=png_bytes)
        return False
    tmp_path = None
    t0 = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        url = uno.systemPathToFileUrl(tmp_path)
        graphic = doc.createInstance("com.sun.star.graphic.GraphicObject")
        if graphic is None:
            _log_shape_add(
                step="png",
                shapes_before=shapes_before,
                create_ms=_mono_ms(t0),
                add_ms=0,
                ok=False,
                png_bytes=len(raw),
            )
            return False
        w, h = _DEFAULT_WIDTH, _PNG_SHAPE_HEIGHT
        create_ms = _mono_ms(t0)
        t1 = time.monotonic()
        graphic.setPosition(stack.place(h))
        graphic.setSize(Size(w, h))
        graphic.GraphicURL = url
        dp.add(graphic)
        add_ms = _mono_ms(t1)
        _log_shape_add(
            step="png",
            shape_h=h,
            shapes_before=shapes_before,
            create_ms=create_ms,
            add_ms=add_ms,
            png_bytes=len(raw),
        )
        return True
    except Exception:
        log.exception("Failed to insert notebook PNG on draw page")
        _log_shape_add(step="png", shapes_before=shapes_before, create_ms=_mono_ms(t0), add_ms=0, ok=False, png_bytes=png_bytes)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _import_png_outputs_on_draw_page(
    doc: Any,
    dp: Any,
    stack: _ImportStackCursor,
    outputs: list[Any],
    cell_index: int,
) -> int:
    """Insert image/png outputs as GraphicObject shapes. Returns number of shapes added."""
    added = 0
    out_list = outputs or []
    if len(out_list) > _MAX_OUTPUTS_PER_CELL:
        out_list = out_list[:_MAX_OUTPUTS_PER_CELL]
    for output in out_list:
        output_type = getattr(output, "output_type", None) or output.get("output_type", "")
        if output_type not in ("display_data", "execute_result"):
            continue
        data = getattr(output, "data", None) or output.get("data", {})
        if not isinstance(data, dict) or "image/png" not in data:
            continue
        b64 = data["image/png"]
        if isinstance(b64, str) and _try_insert_png_on_draw_page(doc, dp, stack, b64):
            added += 1
    return added
'''


def _log_shape_add(
    *,
    step: str,
    name: str = "",
    text_chars: int = 0,
    truncated: bool = False,
    shape_h: int = 0,
    shapes_before: int,
    create_ms: int = 0,
    text_ms: int = 0,
    add_ms: int = 0,
    ok: bool = True,
) -> None:
    total_ms = create_ms + text_ms + add_ms
    log.debug(
        "notebook import add step=%s name=%s text_chars=%d truncated=%s shape_h=%d shapes_before=%d "
        "create_ms=%d text_ms=%d add_ms=%d ok=%s",
        step,
        name,
        text_chars,
        truncated,
        shape_h,
        shapes_before,
        create_ms,
        text_ms,
        add_ms,
        ok,
    )
    if total_ms >= _SLOW_ADD_MS:
        log.warning(
            "notebook import slow UNO add step=%s total_ms=%d shapes_before=%d",
            step,
            total_ms,
            shapes_before,
        )


def flush_ui_idle(ctx: Any | None) -> None:
    if ctx is None:
        return
    try:
        from plugin.framework.uno_context import get_toolkit

        toolkit = get_toolkit(ctx)
        if toolkit is not None and hasattr(toolkit, "processEventsToIdle"):
            toolkit.processEventsToIdle()
    except Exception:
        log.debug("processEventsToIdle failed", exc_info=True)


def _doc_body_nonempty(doc: Any) -> bool:
    try:
        text = doc.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        return bool((cursor.getString() or "").strip())
    except Exception:
        return True


def _append_body_paragraph(doc: Any, content: str, para_style: str | None, *, lead_break: bool) -> None:
    """Append one paragraph to the Writer body (end of document)."""
    if not content and not para_style:
        return
    text = doc.getText()
    cursor = text.createTextCursor()
    cursor.gotoEnd(False)
    if lead_break and _doc_body_nonempty(doc):
        text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
        cursor.gotoEnd(False)
    if para_style:
        try:
            cursor.ParaStyleName = para_style
        except Exception:
            log.debug("ParaStyleName %s failed, using default", para_style, exc_info=True)
    text.insertString(cursor, content, False)


def _append_body_text_block(
    doc: Any,
    block: str,
    para_style: str | None,
    *,
    lead_break: bool = True,
) -> None:
    """Append multiple lines as separate paragraphs."""
    display, _ = _prepare_display_text(block)
    if not display:
        return
    lines = display.split("\n")
    for i, line in enumerate(lines):
        _append_body_paragraph(
            doc,
            line,
            para_style,
            lead_break=lead_break or i > 0,
        )


def _append_cell_heading(doc: Any, title: str, *, lead_break: bool) -> None:
    _append_body_paragraph(doc, title, _STYLE_CELL_HEADING, lead_break=lead_break)


def _append_section_heading(doc: Any, title: str) -> None:
    _append_body_paragraph(doc, title, _STYLE_SECTION_HEADING, lead_break=True)


def _append_code_input_shape(
    doc: Any,
    dp: Any,
    stack: _ImportStackCursor,
    *,
    name: str,
    source: str,
) -> None:
    """Editable code cell: single form TextField on the draw page (only shape per code cell)."""
    shapes_before = stack.shape_count
    display, truncated = _prepare_display_text(_coerce_notebook_text(source))
    raw_chars = len(source or "")

    t0 = time.monotonic()
    model = doc.createInstance("com.sun.star.form.component.TextField")
    if model is None:
        raise RuntimeError("Failed to create form TextField")
    model.Name = name
    if hasattr(model, "Label"):
        model.Label = "Code"
    if hasattr(model, "MultiLine"):
        model.MultiLine = True
    create_ms = _mono_ms(t0)

    t_text = time.monotonic()
    model.Text = display
    text_ms = _mono_ms(t_text)

    h = _height_for_text(display)
    t_shape = time.monotonic()
    shape = doc.createInstance("com.sun.star.drawing.ControlShape")
    if shape is None:
        raise RuntimeError("Failed to create ControlShape")
    shape.setSize(Size(_DEFAULT_WIDTH, h))
    shape.setPosition(stack.place(h))
    shape.Control = model
    create_ms += _mono_ms(t_shape)

    t_add = time.monotonic()
    dp.add(shape)
    add_ms = _mono_ms(t_add)
    _log_shape_add(
        step="code_field",
        name=name,
        text_chars=raw_chars,
        truncated=truncated,
        shape_h=h,
        shapes_before=shapes_before,
        create_ms=create_ms,
        text_ms=text_ms,
        add_ms=add_ms,
    )


def _cell_heading(idx: int, cell_type: str, execution_count: Any | None) -> str:
    title = f"Cell {idx + 1}: {cell_type.capitalize()}"
    if cell_type == "code" and execution_count is not None:
        title += f"  [In [{execution_count}]]"
    return title


def import_ipynb_to_writer(doc: Any, path: str, ctx: Any | None = None) -> dict[str, Any]:
    """Read *path* (.ipynb): body text for markdown/raw/outputs; draw-page field for code only."""
    run_t0 = time.monotonic()
    try:
        file_size = os.path.getsize(path)
    except OSError:
        file_size = -1
    log.info("notebook import start path=%s file_size_bytes=%d", path, file_size)

    read_t0 = time.monotonic()
    nb = read_ipynb(path)
    cell_count = len(nb.cells)
    log.info("notebook import read_ipynb cells=%d read_ms=%d", cell_count, _mono_ms(read_t0))

    dp_t0 = time.monotonic()
    dp = _get_form_draw_page(doc)
    if dp is None:
        raise RuntimeError("No draw page available for form controls.")
    stack = _ImportStackCursor(dp)
    log.debug(
        "notebook import draw page ready seed_ms=%d shapes_on_page=%d",
        _mono_ms(dp_t0),
        stack.shape_count,
    )

    stats = {
        "cells": 0,
        "markdown": 0,
        "code": 0,
        "raw": 0,
        "shapes": 0,
        "outputs": 0,
        # Legacy key for dialog/tests
        "controls": 0,
    }

    _import_cells(doc, dp, stack, nb, stats, cell_count, run_t0)
    flush_ui_idle(ctx)

    stats["controls"] = stats["shapes"]
    total_ms = _mono_ms(run_t0)
    log.info(
        "notebook import complete stats=%s total_ms=%d shapes_final=%d avg_cell_ms=%d",
        stats,
        total_ms,
        stack.shape_count,
        total_ms // max(1, stats["cells"]),
    )
    return stats


def _import_cells(
    doc: Any,
    dp: Any,
    stack: _ImportStackCursor,
    nb: Any,
    stats: dict[str, int],
    cell_count: int,
    run_t0: float,
) -> None:
    first_cell = True
    for idx, cell in enumerate(nb.cells):
        cell_t0 = time.monotonic()
        stats["cells"] += 1
        cell_type = getattr(cell, "cell_type", "raw")
        source = _coerce_notebook_text(getattr(cell, "source", "") or "")
        outputs = list(getattr(cell, "outputs", []) or []) if cell_type == "code" else []
        ec = getattr(cell, "execution_count", None) if cell_type == "code" else None

        log.debug(
            "notebook import cell start index=%d type=%s source_chars=%d output_count=%d shapes=%d",
            idx,
            cell_type,
            len(source),
            len(outputs),
            stack.shape_count,
        )

        lead = not first_cell
        first_cell = False
        _append_cell_heading(doc, _cell_heading(idx, cell_type, ec), lead_break=lead)

        if cell_type == "markdown":
            stats["markdown"] += 1
            _append_body_text_block(doc, source, _STYLE_BODY, lead_break=True)
        elif cell_type == "code":
            stats["code"] += 1
            _append_section_heading(doc, "Code")
            _append_code_input_shape(
                doc,
                dp,
                stack,
                name=f"nb_cell_{idx}_code",
                source=source,
            )
            stats["shapes"] += 1
            '''
            stats["shapes"] += _import_png_outputs_on_draw_page(doc, dp, stack, outputs, idx)
            '''
            out_text = _format_outputs_for_body(outputs, idx)
            if out_text.strip():
                stats["outputs"] += len([o for o in outputs if format_output_text(o).strip()])
                _append_section_heading(doc, "Output")
                _append_body_text_block(doc, out_text, _STYLE_OUTPUT, lead_break=True)
        else:
            stats["raw"] += 1
            _append_body_text_block(doc, source, _STYLE_BODY, lead_break=True)

        log.debug("notebook import cell done index=%d cell_ms=%d shapes=%d", idx, _mono_ms(cell_t0), stack.shape_count)
        if (idx + 1) % _PROGRESS_EVERY_N_CELLS == 0 or idx + 1 == cell_count:
            log.info(
                "notebook import progress cell=%d/%d shapes=%d elapsed_ms=%d",
                idx + 1,
                cell_count,
                stack.shape_count,
                _mono_ms(run_t0),
            )
