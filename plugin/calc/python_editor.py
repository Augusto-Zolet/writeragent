# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open the Monaco editor for the active Calc cell's ``=PYTHON()`` formula."""

from __future__ import annotations

import logging
from typing import Any

from plugin.calc.bridge import CalcBridge
from plugin.calc.python_formula_edit import (
    build_new_python_formula,
    extract_python_code_loose,
    normalize_formula_string,
    parse_python_formula,
    replace_python_code,
)
from plugin.chatbot.dialogs import msgbox
from plugin.framework.i18n import _
from plugin.framework.uno_context import get_desktop
from plugin.scripting.editor_bridge import EditorSession, get_active_session, set_active_session
from plugin.scripting.editor_diagnostics import failure_message
from plugin.scripting.editor_launcher import probe_webview_import, resolve_editor_python, spawn_editor_process

log = logging.getLogger("writeragent.scripting")


def _cell_formula_strings(cell: Any) -> list[str]:
    """Collect formula strings LibreOffice may expose for the cell."""
    out: list[str] = []
    try:
        f = cell.getFormula()
        if f:
            out.append(str(f))
    except Exception:
        pass
    for prop in ("FormulaLocal", "Formula"):
        try:
            val = cell.getPropertyValue(prop)
            if val and str(val) not in out:
                out.append(str(val))
        except Exception:
            pass
    return out


def _parse_cell_python_formula(cell: Any) -> tuple[str, Any | None]:
    """Return (initial editor code, PythonFormulaParts or None) from the cell."""
    for raw in _cell_formula_strings(cell):
        parts = parse_python_formula(raw)
        if parts is not None:
            return parts.code, parts
    for raw in _cell_formula_strings(cell):
        loose = extract_python_code_loose(raw)
        if loose is not None:
            return loose, parse_python_formula(raw)
    return "", None


def _get_active_calc_cell(ctx: Any) -> tuple[Any, Any, str] | None:
    """Return (doc, cell, primary formula string) for the current selection, or None."""
    desktop = get_desktop(ctx)
    if desktop is None:
        log.warning("python_editor: no desktop")
        return None
    frame = desktop.getCurrentFrame()
    if frame is None:
        log.warning("python_editor: no current frame")
        return None
    controller = frame.getController()
    if controller is None:
        log.warning("python_editor: no controller")
        return None
    model = controller.getModel()
    if model is None or not hasattr(model, "getSheets"):
        log.warning("python_editor: not a spreadsheet document")
        return None
    # Match Calc extend/edit: use the sheet controller selection (not formula-bar-only focus).
    cc = model.getCurrentController()
    if cc is None:
        log.warning("python_editor: no CurrentController")
        return None
    selection = cc.getSelection()
    if selection is None:
        log.warning("python_editor: no selection on CurrentController")
        return None
    try:
        addr = selection.getRangeAddress()
    except Exception:
        log.warning("python_editor: selection has no RangeAddress", exc_info=True)
        return None
    bridge = CalcBridge(model)
    sheet = bridge.get_active_sheet()
    cell = bridge.get_cell(sheet, addr.StartColumn, addr.StartRow)
    formulas = _cell_formula_strings(cell)
    formula = formulas[0] if formulas else ""
    log.info("python_editor: cell (%s,%s) formulas=%r", addr.StartColumn, addr.StartRow, formulas)
    return model, cell, formula


def _apply_formula_save(
    doc: Any,
    cell: Any,
    *,
    original_formula: str,
    new_code: str,
    parsed_parts: Any | None,
) -> dict[str, Any]:
    if parsed_parts is not None:
        new_formula = replace_python_code(original_formula, new_code)
        if new_formula is None:
            new_formula = replace_python_code(normalize_formula_string(original_formula), new_code)
    else:
        new_formula = build_new_python_formula(new_code)
    if new_formula is None:
        return {"type": "error", "message": _("Could not rebuild the PYTHON formula.")}
    cell.setFormula(new_formula)
    try:
        doc.calculateAll()
    except Exception:
        log.debug("calculateAll after editor save failed", exc_info=True)
    return {"type": "saved", "ok": True}


def _launch_editor_with_code(
    ctx: Any,
    doc: Any,
    cell: Any,
    *,
    initial_code: str,
    original_formula: str,
    parsed_parts: Any | None,
    exe: str,
) -> None:
    original_formula = original_formula or ""

    def on_save(code: str) -> dict[str, Any]:
        return _apply_formula_save(
            doc,
            cell,
            original_formula=original_formula,
            new_code=code,
            parsed_parts=parsed_parts,
        )

    def on_closed() -> None:
        log.debug("Python cell editor closed")

    try:
        proc = spawn_editor_process(exe)
    except OSError as e:
        log.exception("Failed to spawn editor")
        msgbox(ctx, "WriterAgent", failure_message(_("Could not start the Python editor."), exc=e))
        return

    session = EditorSession(proc, on_save=on_save, on_closed=on_closed)
    set_active_session(session)
    session.start_reader()

    if not session.wait_for_ready(ctx, timeout_sec=45.0):
        detail = session.read_stderr_tail()
        set_active_session(None)
        msgbox(ctx, "WriterAgent", failure_message(_("The Python editor window did not start."), detail=detail))
        return

    if not session.is_running:
        detail = session.read_stderr_tail()
        set_active_session(None)
        msgbox(ctx, "WriterAgent", failure_message(_("The Python editor exited before it could load your code."), detail=detail))
        return

    try:
        session.send({"type": "load", "code": initial_code, "title": _("PYTHON cell editor")})
    except Exception as e:
        log.exception("Failed to send load to editor")
        set_active_session(None)
        msgbox(ctx, "WriterAgent", failure_message(_("Could not talk to the Python editor."), detail=session.read_stderr_tail(), exc=e))
        return


def open_python_cell_editor(ctx: Any) -> None:
    """Launch Monaco editor for the active Calc cell (creates or edits ``=PYTHON()``)."""
    log.info("python_editor: open_python_cell_editor")
    try:
        _open_python_cell_editor_impl(ctx)
    except Exception as e:
        log.exception("python_editor: unhandled failure")
        msgbox(ctx, "WriterAgent", failure_message(_("The Python editor failed unexpectedly."), exc=e))


def _open_python_cell_editor_impl(ctx: Any) -> None:
    existing = get_active_session()
    if existing is not None:
        if existing.is_running:
            msgbox(ctx, "WriterAgent", _("The Python editor is already open."))
            return
        set_active_session(None)

    resolved = _get_active_calc_cell(ctx)
    if resolved is None:
        msgbox(ctx, "WriterAgent", _("Select a cell in a Calc spreadsheet to edit Python."))
        return
    doc, cell, formula = resolved

    initial_code, parsed_parts = _parse_cell_python_formula(cell)
    log.info("python_editor: initial_code len=%s parsed=%s", len(initial_code), parsed_parts is not None)

    exe, err = resolve_editor_python(ctx)
    if not exe:
        msgbox(ctx, "WriterAgent", err or _("No Python interpreter available for the editor."))
        return
    log.info("python_editor: using interpreter %s", exe)

    webview_ok, webview_detail = probe_webview_import(exe)
    log.info("python_editor: webview probe exe=%s ok=%s detail=%r", exe, webview_ok, webview_detail[:200] if webview_detail else "")
    if not webview_ok:
        summary = _(
            "Cannot import webview (pywebview) with the Python from Settings → Python:\n"
            "%(exe)s\n\n"
            "In that venv run: pip install pywebview\n"
            "(import name is webview, package name is pywebview)."
        ) % {"exe": exe}
        msgbox(ctx, "WriterAgent", failure_message(summary, detail=webview_detail or _("unknown error")))
        return

    log.info("python_editor: launching Monaco subprocess")
    _launch_editor_with_code(
        ctx,
        doc,
        cell,
        initial_code=initial_code,
        original_formula=formula,
        parsed_parts=parsed_parts,
        exe=exe,
    )
    log.info("python_editor: editor session started")
