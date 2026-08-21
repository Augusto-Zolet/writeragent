# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the native Edit Python in Cell dialog."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import plugin.calc.python.cell_editor_ui as ui


class _FakeModel:
    def __init__(self, text: str = "", enabled: bool = True) -> None:
        self.Text = text
        self.Label = text
        self.Enabled = enabled
        self.HelpText = ""
        self.State = 0


class _FakeControl:
    def __init__(self, text: str = "", state: int = 0) -> None:
        self._text = text
        self._state = state
        self._model = _FakeModel(text)
        self._model.State = state
        self.action_listeners: list = []
        self.item_listeners: list = []
        self.focus = False

    def getText(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text
        self._model.Text = text

    def getState(self) -> int:
        return self._state

    def setState(self, value: int) -> None:
        self._state = int(value)
        self._model.State = self._state

    def getModel(self) -> _FakeModel:
        return self._model

    def setEnable(self, enabled: bool) -> None:
        self._model.Enabled = bool(enabled)

    def setFocus(self) -> None:
        self.focus = True

    def addActionListener(self, listener: object) -> None:
        self.action_listeners.append(listener)

    def addItemListener(self, listener: object) -> None:
        self.item_listeners.append(listener)


class _FakeDialog:
    def __init__(self) -> None:
        self.controls = {
            "BtnSave": _FakeControl(),
            "BtnCancel": _FakeControl(),
            "ChkPlainText": _FakeControl(state=0),
            "DataLbl": _FakeControl("Data:"),
            "DataEdit": _FakeControl(""),
            "StatusEdit": _FakeControl("Status: Ready"),
            "CodeEdit": _FakeControl(""),
        }
        self.visible = False
        self.disposed = False
        self.top_listeners: list = []

    def getControl(self, name: str) -> _FakeControl:
        return self.controls[name]

    def setVisible(self, visible: bool) -> None:
        self.visible = bool(visible)

    def addTopWindowListener(self, listener: object) -> None:
        self.top_listeners.append(listener)

    def dispose(self) -> None:
        self.disposed = True


def setup_function() -> None:
    ui.reset_native_cell_editor_for_tests()


def teardown_function() -> None:
    ui.reset_native_cell_editor_for_tests()


def _open_native(**kwargs):
    dlg = _FakeDialog()
    with patch.object(ui, "load_writeragent_dialog_detail", return_value=(dlg, None)):
        opened, detail = ui.show_native_python_cell_editor(
            MagicMock(),
            doc=kwargs.get("doc", MagicMock()),
            cell=kwargs.get("cell", MagicMock()),
            initial_code=kwargs.get("initial_code", "print(1)"),
            parsed_parts=kwargs.get("parsed_parts", None),
        )
    assert opened is True
    assert detail is None
    return dlg, ui._active


def test_native_load_plain_cell_checks_save_without_py():
    dlg, inst = _open_native(initial_code="print(1)", parsed_parts=None)
    assert dlg.controls["CodeEdit"].getText() == "print(1)"
    assert dlg.controls["ChkPlainText"].getState() == 1
    assert dlg.controls["DataEdit"]._model.Enabled is False
    assert "Ready" in dlg.controls["StatusEdit"].getText()
    assert inst is not None
    assert inst.is_open


def test_native_load_formula_cell_unchecks_plain():
    parts = SimpleNamespace(data_suffix="; A1:B2")
    with patch(
        "plugin.calc.python.formula_edit.format_data_binding_display",
        return_value="A1:B2",
    ):
        dlg, unused = _open_native(initial_code="result = 1", parsed_parts=parts)
    assert dlg.controls["ChkPlainText"].getState() == 0
    assert dlg.controls["DataEdit"].getText() == "A1:B2"
    assert dlg.controls["DataEdit"]._model.Enabled is True


def test_native_save_formula_mode():
    dlg, inst = _open_native(initial_code="result = 2", parsed_parts=None)
    dlg.controls["ChkPlainText"].setState(0)
    inst._sync_data_enabled()
    dlg.controls["DataEdit"].setText("C1:C2")
    dlg.controls["CodeEdit"].setText("result = 3")
    with patch(
        "plugin.calc.python.editor._apply_cell_save",
        return_value={"type": "saved", "ok": True, "save_as_plain": False},
    ) as mock_save:
        inst._save()
    mock_save.assert_called_once()
    kwargs = mock_save.call_args.kwargs
    assert kwargs["new_code"] == "result = 3"
    assert kwargs["save_as_plain"] is False
    assert kwargs["data_binding_text"] == "C1:C2"
    assert "Saved." in dlg.controls["StatusEdit"].getText()


def test_native_save_plain_mode():
    dlg, inst = _open_native(initial_code="print(1)", parsed_parts=None)
    with patch(
        "plugin.calc.python.editor._apply_cell_save",
        return_value={
            "type": "saved",
            "ok": True,
            "save_as_plain": True,
            "status_ok_text": "Saved without =PY().",
        },
    ) as mock_save:
        inst._save()
    assert mock_save.call_args.kwargs["save_as_plain"] is True
    assert mock_save.call_args.kwargs["data_binding_text"] is None
    assert "Saved without =PY()." in dlg.controls["StatusEdit"].getText()


def test_native_save_error_status():
    dlg, inst = _open_native(initial_code="x", parsed_parts=None)
    with patch(
        "plugin.calc.python.editor._apply_cell_save",
        return_value={"type": "error", "message": "could not rewrite"},
    ):
        inst._save()
    assert "could not rewrite" in dlg.controls["StatusEdit"].getText()


def test_native_retarget_reloads_code():
    dlg, inst = _open_native(initial_code="a = 1", parsed_parts=None)
    cell_b = MagicMock()
    inst.retarget(doc=MagicMock(), cell=cell_b, initial_code="a = 2", parsed_parts=None)
    assert dlg.controls["CodeEdit"].getText() == "a = 2"
    assert inst._cell is cell_b


def test_native_cancel_disposes():
    dlg, inst = _open_native(initial_code="x", parsed_parts=None)
    inst.close()
    assert dlg.disposed is True
    assert inst.is_open is False
    assert ui._active is None


def test_native_second_open_retargets_same_dialog():
    dlg1, inst1 = _open_native(initial_code="first", parsed_parts=None)
    with patch.object(ui, "load_writeragent_dialog_detail") as mock_load:
        opened, unused = ui.show_native_python_cell_editor(
            MagicMock(),
            doc=MagicMock(),
            cell=MagicMock(),
            initial_code="second",
            parsed_parts=None,
        )
    assert opened is True
    mock_load.assert_not_called()
    assert ui._active is inst1
    assert dlg1.controls["CodeEdit"].getText() == "second"
