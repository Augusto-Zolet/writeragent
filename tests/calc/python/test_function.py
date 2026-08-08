# WriterAgent - =PYTHON() return coercion tests

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import plugin.calc.python.function as python_function
from plugin.calc.python.function import finalize_python_return, to_calc_compatible
from plugin.tests.testing_utils import CalcDocStub


def _ctx_with_doc(doc: CalcDocStub):
    desktop = MagicMock()
    desktop.getCurrentComponent.return_value = doc
    smgr = MagicMock()
    smgr.createInstanceWithContext.return_value = desktop
    return SimpleNamespace(ServiceManager=smgr)


def test_to_calc_compatible_none_becomes_empty_nan_becomes_error() -> None:
    """None (from text/mixed or explicit) becomes empty cell; NaN is returned raw (Calc shows cascading error)."""
    import math
    assert to_calc_compatible(None) == ""
    assert math.isnan(to_calc_compatible(float("nan")))


def test_to_calc_compatible_finite_float_unchanged() -> None:
    assert to_calc_compatible(3.5) == 3.5


def test_to_calc_compatible_nan_in_nested_matrix() -> None:
    """NaN slots in a matrix result stay as NaN (Calc error cells); only None becomes empty."""
    import math
    matrix = ((1.0, float("nan")), (3.0, 4.0))
    out = to_calc_compatible(matrix)
    assert out[0][0] == 1.0
    assert math.isnan(out[0][1])
    assert out[1] == (3.0, 4.0)


def test_finalize_python_return_scalar_nan_becomes_error() -> None:
    """Scalar NaN from worker becomes a Calc error (not silent empty)."""
    import math
    class _Ctx:
        pass

    val = finalize_python_return(_Ctx(), "c", float("nan"))
    assert math.isnan(val)


def test_finalize_python_return_list_nan_becomes_error() -> None:
    """NaN inside a list result becomes nan via to_calc_compatible (Calc error). The matrix session path uses the same coercion."""
    import math
    # Direct coercion for the element (the session path in finalize calls to_calc_compatible on each)
    assert math.isnan(to_calc_compatible(float("nan")))
    # Also exercise finalize with a fresh context (no prior session) for a single nan scalar
    class _Ctx:
        pass
    val = finalize_python_return(_Ctx(), "c2", float("nan"))
    assert math.isnan(val)


@pytest.mark.parametrize("nan_val", [math.nan, float("nan")])
def test_to_calc_compatible_various_nan_literals(nan_val: float) -> None:
    """Any spelling of NaN is returned raw (Calc error), not coerced to empty."""
    import math
    assert math.isnan(to_calc_compatible(nan_val))


def test_insert_image_result_uses_merged_safe_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    class _TmpFile:
        name = "/tmp/fake.png"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def write(self, _data):
            return None

    import plugin.scripting.payload_codec as payload_codec

    monkeypatch.setattr(payload_codec.tempfile, "NamedTemporaryFile", lambda **kwargs: _TmpFile())

    class _UnoModule:
        @staticmethod
        def systemPathToFileUrl(path: str) -> str:
            return f"file://{path}"

    import sys

    monkeypatch.setitem(sys.modules, "uno", _UnoModule())
    awt_mod = SimpleNamespace(Size=lambda w, h: ("Size", w, h))
    monkeypatch.setitem(sys.modules, "com.sun.star.awt", awt_mod)

    doc = CalcDocStub(selection="C4")
    shape = MagicMock()
    doc._created["com.sun.star.drawing.GraphicObjectShape"] = shape
    sheet = doc.getSheets().getByName("Sheet1")
    cell = sheet.getCellByPosition(2, 3)
    ctx = _ctx_with_doc(doc)

    pos = SimpleNamespace(X=111, Y=222)
    size = SimpleNamespace(Width=333, Height=444)
    import plugin.calc.calc_utils as calc_utils

    monkeypatch.setattr(calc_utils, "get_cell_geometry", lambda _sheet, _cell: (pos, size))

    python_function.insert_image_result_on_sheet(ctx, {"data": b"abc", "format": "png"})

    shape.setPosition.assert_called_once_with(pos)
    shape.setSize.assert_any_call(size)
    shape.setPropertyValue.assert_any_call("Anchor", cell)
    shape.setPropertyValue.assert_any_call("ResizeWithCell", True)


def test_finalize_python_return_triggers_spill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a list result triggers deferred spilling when not in a matrix selection."""
    doc = CalcDocStub(url="file:///fake.ods", selection="B2")
    sheet = doc.getSheets().getByName("Sheet1")
    sheet.getCellByPosition(1, 1).setFormula('=PYTHON("test_code")')
    ctx = _ctx_with_doc(doc)

    python_function.SPILL_REGISTRY.clear()

    class DummyTimer:
        def __init__(self, interval, function, args=(), kwargs={}):
            self.function = function
            self.args = args
            self.kwargs = kwargs
        def start(self):
            self.function(*self.args, **self.kwargs)

    monkeypatch.setattr(python_function.threading, "Timer", DummyTimer)
    # Deferred spill posts to the main-thread queue; run immediately in unit tests.
    monkeypatch.setattr(
        "plugin.framework.queue_executor.post_to_main_thread",
        lambda fn, *a, **k: fn(*a, **k),
    )
    python_function.LOADED_DOCUMENTS.clear()

    result = [10.0, 20.0]  # 1D list, will be treated as shape (2, 1)
    val = finalize_python_return(ctx, "test_code", result)

    assert val == 10.0
    # B2 is the formula cell (left alone); spill writes B3 via setDataArray.
    assert sheet.getCellByPosition(1, 2).getValue() == 20.0

    key = ("file:///fake.ods", sheet.getName(), 1, 1)
    assert key in python_function.SPILL_REGISTRY
    assert python_function.SPILL_REGISTRY[key] == [(2, 1)]


def test_finalize_python_return_matrix_formula_does_not_spill() -> None:
    """Test that a matrix selection (e.g. B2:C3) does not trigger spilling, but returns standard scalar instead."""
    doc = CalcDocStub()
    sheet = doc.getSheets().getByName("Sheet1")
    # EndColumn > StartColumn means it is a matrix selection
    doc.CurrentController.Selection = sheet.getCellRangeByPosition(1, 1, 2, 1)
    ctx = _ctx_with_doc(doc)

    result = [[1.0, 2.0], [3.0, 4.0]]
    val = finalize_python_return(ctx, "test_code_matrix", result)

    # Should fall back to standard scalar/session returns for matrix formula
    assert val == 1.0


def test_spill_collision_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that finalize_python_return returns #SPILL! when a cell in the spill target is occupied."""
    doc = CalcDocStub(url="file:///fake.ods", selection="B2")
    sheet = doc.getSheets().getByName("Sheet1")
    sheet.getCellByPosition(1, 1).setFormula('=PYTHON("test_code_spill_blocked")')
    # Occupied spill target (getType() != EMPTY)
    sheet.getCellByPosition(1, 2).setValue(1.0)
    ctx = _ctx_with_doc(doc)

    python_function.SPILL_REGISTRY.clear()
    python_function.LOADED_DOCUMENTS.clear()

    val = finalize_python_return(ctx, "test_code_spill_blocked", [[100], [200]])

    assert val == "#SPILL!"
    key = ("file:///fake.ods", "Sheet1", 1, 1)
    assert python_function.SPILL_REGISTRY.get(key) is None


def test_load_and_save_spill_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that spill registry loads from and saves to document properties correctly."""
    import json

    saved_payload = None

    def mock_get_prop(model, name, default=None):
        if name == "WriterAgentSpillRegistry":
            return json.dumps({
                "Sheet1:1,1": [[2, 1], [3, 1]]
            })
        return default

    def mock_set_prop(model, name, value):
        nonlocal saved_payload
        if name == "WriterAgentSpillRegistry":
            saved_payload = value

    monkeypatch.setattr("plugin.doc.document_helpers.get_document_property", mock_get_prop)
    monkeypatch.setattr("plugin.doc.document_helpers.set_document_property", mock_set_prop)

    doc = CalcDocStub(url="file:///fake_doc.ods")

    python_function.SPILL_REGISTRY.clear()
    python_function.LOADED_DOCUMENTS.clear()

    python_function.load_spill_registry_for_doc(doc)
    key = ("file:///fake_doc.ods", "Sheet1", 1, 1)
    assert key in python_function.SPILL_REGISTRY
    assert python_function.SPILL_REGISTRY[key] == [(2, 1), (3, 1)]

    python_function.SPILL_REGISTRY[key] = [(2, 1), (3, 1), (4, 1)]
    python_function.save_spill_registry_for_doc(doc)

    assert saved_payload is not None
    data = json.loads(saved_payload)
    assert data["Sheet1:1,1"] == [[2, 1], [3, 1], [4, 1]]


def test_session_key_and_init_kwargs_recursion_off_main_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set WRITERAGENT_TESTING to 1 to force inline execution in queue_executor
    monkeypatch.setenv("WRITERAGENT_TESTING", "1")

    monkeypatch.setattr("plugin.framework.thread_guard.on_main_thread", lambda: False)

    doc = CalcDocStub(url="file:///fake_recursion.ods")
    sheet = doc.getSheets().getByName("Sheet1")
    sheet._name = "SheetTest"

    monkeypatch.setattr("plugin.calc.python.function._get_calc_doc", lambda ctx: doc)
    monkeypatch.setattr("plugin.calc.python.function.get_calc_document_from_ctx", lambda ctx: doc)
    monkeypatch.setattr("plugin.calc.python.function.build_python_eval_init_kwargs", lambda doc: {"dummy": True})

    ctx = MagicMock()
    key = python_function.session_key(ctx, "print('hello')")
    assert key == ("file:///fake_recursion.ods", "SheetTest", "print('hello')")

    kwargs = python_function.get_python_init_kwargs(ctx)
    assert kwargs == {"dummy": True}


def test_finalize_python_return_triggers_spill_2d(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a 2D result triggers block spills via setDataArray on appropriate ranges."""
    doc = CalcDocStub(url="file:///fake2d.ods", selection="B2")
    sheet = doc.getSheets().getByName("Sheet1")
    sheet.getCellByPosition(1, 1).setFormula('=PYTHON("test_code_2d")')
    ctx = _ctx_with_doc(doc)

    python_function.SPILL_REGISTRY.clear()

    class DummyTimer:
        def __init__(self, interval, function, args=(), kwargs={}):
            self.function = function
            self.args = args
            self.kwargs = kwargs
        def start(self):
            self.function(*self.args, **self.kwargs)

    monkeypatch.setattr(python_function.threading, "Timer", DummyTimer)
    monkeypatch.setattr(
        "plugin.framework.queue_executor.post_to_main_thread",
        lambda fn, *a, **k: fn(*a, **k),
    )
    python_function.LOADED_DOCUMENTS.clear()

    result = [[10.0, 20.0], [30.0, 40.0]]
    val = finalize_python_return(ctx, "test_code_2d", result)

    assert val == 10.0
    assert sheet.getCellByPosition(2, 1).getValue() == 20.0  # C2
    assert sheet.getCellByPosition(1, 2).getValue() == 30.0  # B3
    assert sheet.getCellByPosition(2, 2).getValue() == 40.0  # C3

    key = ("file:///fake2d.ods", "Sheet1", 1, 1)
    assert key in python_function.SPILL_REGISTRY
    assert set(python_function.SPILL_REGISTRY[key]) == {(1, 2), (2, 1), (2, 2)}


def test_calc_spill_modify_listener_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CalcSpillModifyListener cleans up spilled cells when formula is removed."""
    # Listener cleanup asserts clearContents call args; keep a MagicMock sheet for that.
    sheet = MagicMock()
    aEvent = SimpleNamespace(Source=sheet)
    doc = CalcDocStub(url="file:///fake_cleanup.ods")

    monkeypatch.setattr(python_function, "_get_calc_doc", lambda ctx: doc)

    saved = []
    monkeypatch.setattr(python_function, "save_spill_registry_for_doc", lambda d: saved.append(d))

    ctx = MagicMock()
    listener = python_function.CalcSpillModifyListener(ctx, "file:///fake_cleanup.ods", "Sheet1")

    key = ("file:///fake_cleanup.ods", "Sheet1", 1, 1)
    python_function.SPILL_REGISTRY[key] = [(2, 1)]

    cell_B2 = MagicMock()
    cell_B3 = MagicMock()

    def get_cell(c, r):
        if r == 1 and c == 1:
            return cell_B2
        if r == 2 and c == 1:
            return cell_B3
        return MagicMock()

    sheet.getCellByPosition.side_effect = get_cell

    cell_B2.getFormula.return_value = '=PYTHON("some_code")'
    listener.modified(aEvent)

    assert key in python_function.SPILL_REGISTRY
    cell_B3.clearContents.assert_not_called()

    cell_B2.getFormula.return_value = ''
    listener.modified(aEvent)

    assert key not in python_function.SPILL_REGISTRY
    cell_B3.clearContents.assert_called_once_with(23)
    assert len(saved) == 1
