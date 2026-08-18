# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for LibrePy Python sidebar helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from plugin.librepy.python_sidebar import (
    _MIN_FLEX_HEIGHT,
    _PanelResizeListener,
    compute_python_sidebar_layout,
    format_runtime_status,
    workbook_key_for_doc,
)


def _xdl_snapshot():
    """Positions from extension/Dialogs/PythonSidebarDialog.xdl."""
    return {
        "status_label": (4, 4, 172, 10),
        "status": (4, 14, 172, 28),
        "btn_refresh": (4, 46, 54, 14),
        "btn_edit_cell": (62, 46, 54, 14),
        "btn_run_script": (120, 46, 56, 14),
        "cells_label": (4, 64, 172, 10),
        "cells_list": (4, 76, 172, 70),
        "filter_label": (4, 150, 40, 10),
        "filter_combo": (44, 148, 132, 14),
        "diag_label": (4, 166, 172, 10),
        "diag_list": (4, 178, 172, 50),
        "diag_detail": (4, 232, 172, 70),
        "btn_edit_init": (4, 308, 84, 14),
        "btn_reset": (92, 308, 84, 14),
        "btn_settings": (4, 326, 172, 14),
    }


def _mock_control(x, y, width, height):
    ctrl = MagicMock()
    pos = SimpleNamespace(X=x, Y=y, Width=width, Height=height)

    def set_pos_size(nx, ny, nw, nh, _flags):
        pos.X, pos.Y, pos.Width, pos.Height = nx, ny, nw, nh

    ctrl.getPosSize.return_value = pos
    ctrl.setPosSize.side_effect = set_pos_size
    return ctrl


def test_format_runtime_status_isolated_embedded():
    ctx = MagicMock()
    with (
        patch("plugin.librepy.python_sidebar.python_session_mode", return_value="isolated"),
        patch("plugin.librepy.python_sidebar.get_config_str", return_value=""),
    ):
        text = format_runtime_status(ctx, None)
    assert "Isolated" in text
    assert "embedded" in text.lower() or "LibreOffice" in text


def test_format_runtime_status_shared_with_venv():
    ctx = MagicMock()
    with (
        patch("plugin.librepy.python_sidebar.python_session_mode", return_value="shared"),
        patch("plugin.librepy.python_sidebar.get_config_str", return_value="/tmp/myvenv"),
        patch("plugin.librepy.python_sidebar.resolve_venv_python", return_value="/tmp/myvenv/bin/python"),
    ):
        text = format_runtime_status(ctx, None)
    assert "Shared" in text
    assert "/tmp/myvenv" in text


def test_workbook_key_for_doc_uses_session_id():
    doc = MagicMock()
    with patch(
        "plugin.librepy.python_sidebar.calc_workbook_base_session_id",
        return_value="calc:file:///tmp/a.ods",
    ):
        assert workbook_key_for_doc(doc) == "calc:file:///tmp/a.ods"


def test_workbook_key_unknown_on_none():
    assert workbook_key_for_doc(None) == "unknown"


def test_python_sidebar_xdl_uses_menulist_not_listbox():
    """LibreOffice dialog.dtd has dlg:menulist only; dlg:listbox breaks createContainerWindow
    and aborts soffice with 'pure virtual method called' when the Calc sidebar opens."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    # Repo: extension/Dialogs/; make release bundle: Dialogs/ at OXT root.
    candidates = (
        root / "extension" / "Dialogs" / "PythonSidebarDialog.xdl",
        root / "Dialogs" / "PythonSidebarDialog.xdl",
    )
    xdl = next((p for p in candidates if p.is_file()), None)
    assert xdl is not None, f"PythonSidebarDialog.xdl not found under {root} (tried {[str(p) for p in candidates]})"
    text = xdl.read_text(encoding="utf-8")
    assert "dlg:listbox" not in text
    assert 'dlg:id="cells_list"' in text and "dlg:menulist" in text
    assert 'dlg:id="diag_list"' in text


def test_activation_listener_schedules_refresh():
    """Switching sheets fires _schedule_refresh via the activation listener."""
    from plugin.librepy.python_sidebar import PythonSidebarController

    ctrl = PythonSidebarController.__new__(PythonSidebarController)
    refresh_calls = []
    ctrl._schedule_refresh = lambda *_: refresh_calls.append(1)

    # _Activation is a private class; import and instantiate it directly.
    from plugin.librepy.python_sidebar import _Activation  # type: ignore[attr-defined]

    listener = _Activation(ctrl._schedule_refresh)
    listener.activeSpreadsheetChanged(object())
    assert refresh_calls, "_schedule_refresh should be called when active sheet changes via activeSpreadsheetChanged"


def test_sidebar_prefers_frame_document_over_desktop():
    from plugin.librepy.python_sidebar import PythonSidebarController

    frame = MagicMock()
    model = MagicMock()
    frame.getController.return_value.getModel.return_value = model
    ctrl = PythonSidebarController.__new__(PythonSidebarController)
    ctrl.ctx = MagicMock()
    ctrl.frame = frame
    with (
        patch("plugin.librepy.python_sidebar.is_calc", return_value=True),
        patch("plugin.framework.thread_guard.guard_uno", side_effect=lambda m: m),
        patch("plugin.librepy.python_sidebar.get_calc_document_from_ctx") as fallback,
    ):
        assert ctrl._calc_document() is model
    fallback.assert_not_called()


def test_layout_identity_at_xdl_height():
    snapshot = _xdl_snapshot()
    layouts = compute_python_sidebar_layout(180, 360, snapshot)
    assert layouts == snapshot


def test_layout_widths_unchanged_when_taller():
    snapshot = _xdl_snapshot()
    layouts = compute_python_sidebar_layout(180, 500, snapshot)
    flex = {"status", "cells_list", "diag_list", "diag_detail"}
    for name, (ox, oy, ow, oh) in snapshot.items():
        nx, ny, nw, nh = layouts[name]
        assert nx == ox and nw == ow
        if name in flex:
            assert nh > oh
            assert ny >= oy
        else:
            assert nh == oh


def test_layout_preserves_xdl_gaps_and_grows_flex_by_snapshot_ratio():
    snapshot = _xdl_snapshot()
    layouts = compute_python_sidebar_layout(180, 500, snapshot)
    status = layouts["status"]
    refresh = layouts["btn_refresh"]
    assert refresh[1] - (status[1] + status[3]) == 4
    leftover = 500 - 20 - (340 - 218)
    assert layouts["status"][3] == leftover * 28 // 218
    assert layouts["cells_list"][3] == leftover * 70 // 218
    assert layouts["diag_list"][3] == leftover * 50 // 218
    assigned = layouts["status"][3] + layouts["cells_list"][3] + layouts["diag_list"][3]
    assert layouts["diag_detail"][3] == leftover - assigned
    short = compute_python_sidebar_layout(180, 360, snapshot)
    tall = compute_python_sidebar_layout(180, 700, snapshot)
    for name in ("status", "cells_list", "diag_list", "diag_detail"):
        assert tall[name][3] > short[name][3]


def test_layout_short_panel_keeps_minimum_flex_height():
    layouts = compute_python_sidebar_layout(180, 200, _xdl_snapshot())
    for name in ("status", "cells_list", "diag_list", "diag_detail"):
        assert layouts[name][3] >= _MIN_FLEX_HEIGHT


def test_resize_listener_applies_layout():
    snapshot = _xdl_snapshot()
    controls = {name: _mock_control(x, y, w, h) for name, (x, y, w, h) in snapshot.items()}
    root = MagicMock()
    root.getPosSize.return_value = SimpleNamespace(Width=180, Height=500)
    listener = _PanelResizeListener(controls)
    listener.relayout_now(root)
    expected = compute_python_sidebar_layout(180, 500, snapshot)
    for name, (ex, ey, ew, eh) in expected.items():
        ps = controls[name].getPosSize()
        assert (ps.X, ps.Y, ps.Width, ps.Height) == (ex, ey, ew, eh)
