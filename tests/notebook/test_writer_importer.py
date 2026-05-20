# WriterAgent - tests for notebook Writer import helpers

from __future__ import annotations

from unittest.mock import MagicMock

from plugin.notebook.writer_importer import (
    _ImportStackCursor,
    _MAX_IMPORT_TEXT_CHARS,
    _coerce_notebook_text,
    _prepare_display_text,
    format_all_outputs,
    format_output_text,
    import_ipynb_to_writer,
)


def test_format_stream_output():
    class Out:
        output_type = "stream"
        name = "stdout"
        text = "hello\n"

    assert format_output_text(Out()) == "[stdout]\nhello\n"


def test_format_error_strips_ansi():
    out = {"output_type": "error", "traceback": "\x1b[31mValueError\x1b[0m: bad"}
    assert "ValueError" in format_output_text(out)
    assert "\x1b" not in format_output_text(out)


def test_format_execute_result_plain():
    out = {"output_type": "execute_result", "data": {"text/plain": "42"}}
    assert format_output_text(out) == "42"


def test_coerce_notebook_text_joins_list():
    assert _coerce_notebook_text(["a\n", "b\n"]) == "a\nb\n"


def test_prepare_display_text_truncates():
    long_text = "x" * (_MAX_IMPORT_TEXT_CHARS + 1000)
    display, truncated = _prepare_display_text(long_text)
    assert truncated is True
    assert len(display) <= _MAX_IMPORT_TEXT_CHARS + 50


def test_format_output_image_omitted():
    out = {"output_type": "display_data", "data": {"image/png": "abc"}}
    assert "omitted" in format_output_text(out)


def test_format_output_plain_mime():
    out = {"output_type": "display_data", "data": {"text/html": "<p>x</p>", "text/plain": "hi"}}
    assert format_output_text(out) == "hi"


def test_format_all_outputs_joins():
    outputs = [
        {"output_type": "stream", "name": "stdout", "text": "a"},
        {"output_type": "execute_result", "data": {"text/plain": "b"}},
    ]
    text = format_all_outputs(outputs)
    assert "a" in text and "b" in text


class _FakePoint:
    def __init__(self, x, y):
        self.X = x
        self.Y = y


def test_import_stack_cursor_place_advances(monkeypatch):
    monkeypatch.setattr("plugin.notebook.writer_importer.Point", _FakePoint)
    dp = MagicMock()
    dp.getCount.return_value = 0
    stack = _ImportStackCursor(dp)
    stack.place(700)
    first_bottom = stack._max_bottom
    stack.place(600)
    assert stack.shape_count == 2
    assert first_bottom == 800 + 400 + 700
    assert stack._max_bottom == first_bottom + 400 + 600


def test_import_stack_cursor_seeds_existing_shapes(monkeypatch):
    monkeypatch.setattr("plugin.notebook.writer_importer.Point", _FakePoint)
    shape = MagicMock()
    shape.getPosition.return_value = MagicMock(Y=1000, X=0)
    shape.getSize.return_value = MagicMock(Height=500, Width=100)
    dp = MagicMock()
    dp.getCount.return_value = 1
    dp.getByIndex.return_value = shape
    stack = _ImportStackCursor(dp)
    assert stack.shape_count == 1
    assert stack._max_bottom == 1500
    stack.place(100)
    assert stack._max_bottom == 1500 + 400 + 100


def test_import_ipynb_to_writer_logs(caplog, tmp_path, monkeypatch):
    ipynb = tmp_path / "tiny.ipynb"
    ipynb.write_text(
        '{"nbformat":4,"nbformat_minor":5,"metadata":{},"cells":[{"cell_type":"markdown","metadata":{},"source":"hi"}]}',
        encoding="utf-8",
    )

    shapes: list[MagicMock] = []

    class FakePoint:
        def __init__(self, x, y):
            self.X = x
            self.Y = y

    class FakeSize:
        def __init__(self, w, h):
            self.Width = w
            self.Height = h

    dp = MagicMock()
    dp.getCount.return_value = 0
    dp.add.side_effect = lambda s: shapes.append(s)

    doc = MagicMock()
    doc.getDrawPage.return_value = dp
    body_cursor = MagicMock()
    body_text = MagicMock()
    body_text.createTextCursor.return_value = body_cursor
    doc.getText.return_value = body_text

    def fake_create(service):
        m = MagicMock()
        m.getPosition.return_value = FakePoint(0, 0)
        m.getSize.return_value = FakeSize(100, 100)
        return m

    doc.createInstance.side_effect = fake_create

    monkeypatch.setattr("plugin.notebook.writer_importer._get_form_draw_page", lambda d: dp)
    monkeypatch.setattr("plugin.notebook.writer_importer.Point", FakePoint)
    monkeypatch.setattr("plugin.notebook.writer_importer.Size", FakeSize)

    with caplog.at_level("DEBUG", logger="writeragent.notebook"):
        stats = import_ipynb_to_writer(doc, str(ipynb))

    assert stats["cells"] == 1
    assert stats["markdown"] == 1
    assert "notebook import start" in caplog.text
    assert "notebook import complete" in caplog.text
    assert "cell start index=0" in caplog.text
