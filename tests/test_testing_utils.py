# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for shared pytest stubs in testing_utils."""

import pytest

from plugin.framework.tool import ToolContext
from plugin.tests.testing_utils import CalcDocStub, MockContext, TestingFactory, WriterDocStub


def test_calc_doc_stub_defaults():
    doc = CalcDocStub()
    assert doc.supportsService("com.sun.star.sheet.SpreadsheetDocument")
    assert not doc.supportsService("com.sun.star.text.TextDocument")
    assert doc.getURL() == "test://calc"
    sheets = doc.getSheets()
    assert sheets.getCount() == 1
    assert sheets.hasByName("Sheet1")
    sheet = sheets.getByName("Sheet1")
    assert sheet.getName() == "Sheet1"
    assert doc.getCurrentController().getActiveSheet() is sheet
    assert doc.CurrentController.ActiveSheet is sheet
    sel = doc.CurrentController.Selection
    addr = sel.getRangeAddress()
    assert (addr.StartColumn, addr.StartRow, addr.EndColumn, addr.EndRow) == (0, 0, 0, 0)


def test_calc_doc_stub_seed_data_and_a1_range():
    doc = CalcDocStub(data=(("hello", 2.5), ("=A1", "")))
    sheet = doc.getSheets().getByIndex(0)
    assert sheet.getCellByPosition(0, 0).getString() == "hello"
    assert sheet.getCellByPosition(1, 0).getValue() == 2.5
    assert sheet.getCellByPosition(0, 1).getFormula() == "=A1"
    b2 = sheet.getCellRangeByName("B2")
    assert b2.getRangeAddress().StartColumn == 1
    assert b2.getRangeAddress().StartRow == 1
    rng = sheet.getCellRangeByName("A1:B1")
    assert rng.getDataArray() == (("hello", 2.5),)


def test_calc_doc_stub_insert_sheet_and_selection_override():
    doc = CalcDocStub(selection="B2")
    sheets = doc.getSheets()
    sheets.insertNewByName("Extra", 1)
    assert sheets.hasByName("Extra")
    assert sheets.getCount() == 2
    assert sheets.getByIndex(1).getName() == "Extra"
    addr = doc.getCurrentController().getSelection().getRangeAddress()
    assert (addr.StartColumn, addr.StartRow) == (1, 1)


def test_testing_factory_create_doc_calc():
    doc = TestingFactory.create_doc(doc_type="calc")
    assert isinstance(doc, CalcDocStub)
    assert doc.supportsService("com.sun.star.sheet.SpreadsheetDocument")
    assert doc.getSheets().hasByName("Sheet1")

    seeded = TestingFactory.create_doc(doc_type="calc", data=(("x",),))
    assert seeded.getSheets().getByIndex(0).getCellByPosition(0, 0).getString() == "x"


def test_calc_sheet_query_content_cells_formulas():
    doc = CalcDocStub(
        data=(
            ('=PY("a")', "plain"),
            ("=SUM(A1)", '=PY("b")'),
        )
    )
    sheet = doc.getSheets().getByName("Sheet1")
    enum = sheet.queryContentCells(16)
    assert enum.getCount() == 1
    rng = enum.getByIndex(0)
    addr = rng.getRangeAddress()
    assert (addr.StartColumn, addr.StartRow, addr.EndColumn, addr.EndRow) == (0, 0, 1, 1)
    formulas = rng.getFormulas()
    assert formulas[0][0] == '=PY("a")'
    assert formulas[1][1] == '=PY("b")'


def test_calc_doc_stub_calculate_all_and_props_listeners():
    doc = CalcDocStub(props={"RuntimeUID": "uid-1"})
    assert doc.getPropertyValue("RuntimeUID") == "uid-1"
    doc.setPropertyValue("RuntimeUID", "uid-2")
    assert doc.getPropertyValue("RuntimeUID") == "uid-2"
    doc.calculateAll()
    doc.calculateAll()
    assert doc.calculate_all_count == 2
    doc.addDocumentEventListener(object())
    assert len(doc._document_event_listeners) == 1


def test_testing_factory_create_doc_writer():
    doc = TestingFactory.create_doc(doc_type="writer")
    assert isinstance(doc, WriterDocStub)
    assert doc.supportsService("com.sun.star.text.TextDocument")
    assert not doc.supportsService("com.sun.star.sheet.SpreadsheetDocument")

    seeded = TestingFactory.create_doc(
        doc_type="writer",
        content=[],
        items={"ParagraphStyles": object()},
    )
    assert isinstance(seeded, WriterDocStub)
    assert seeded.getStyleFamilies().hasByName("ParagraphStyles")
    assert seeded.getStyleFamilies().getElementNames() == ("ParagraphStyles",)


def test_testing_factory_create_context_mock():
    writer_ctx = TestingFactory.create_context(doc_type="writer")
    assert isinstance(writer_ctx, ToolContext)
    assert isinstance(writer_ctx.doc, WriterDocStub)
    assert isinstance(writer_ctx.ctx, MockContext)
    assert writer_ctx.doc_type == "writer"

    calc_ctx = TestingFactory.create_context(doc_type="calc")
    assert isinstance(calc_ctx.doc, CalcDocStub)
    assert calc_ctx.doc_type == "calc"


def test_testing_factory_create_context_native_requires_doc():
    with pytest.raises(ValueError, match="requires doc="):
        TestingFactory.create_context(env="native", doc_type="writer")


def test_testing_factory_execute_tool_unknown_name():
    from unittest.mock import MagicMock, patch

    doc = CalcDocStub()
    ctx = MockContext()
    fake_tools = MagicMock()
    fake_tools.execute.side_effect = KeyError("bad_tool")
    with (
        patch("plugin.main.get_tools", return_value=fake_tools),
        patch("plugin.main.get_services", return_value={}),
    ):
        res = TestingFactory.execute_tool(doc, ctx, "bad_tool", {}, doc_type="calc")
    assert res["status"] == "error"
    assert "bad_tool" in res["error"]
