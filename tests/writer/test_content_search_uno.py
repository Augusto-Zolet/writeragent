# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Integration tests for native regex-based and chaining-based content searches.
import uno  # noqa: F401

from plugin.testing_runner import native_test, setup, teardown
from plugin.writer.content import _find_first_range, _find_all_ranges
from plugin.tests.testing_utils import TestingFactory

_test_doc = None
_test_ctx = None


@setup
def my_setup(ctx):
    global _test_doc, _test_ctx
    _test_ctx = ctx
    _test_doc = TestingFactory.create_native_doc(ctx, doc_type="writer", hidden=True)


@teardown
def my_teardown(ctx):
    global _test_doc
    if _test_doc:
        _test_doc.close(True)
    _test_doc = None


@native_test
def test_search_multi_paragraph_body_uno():
    """Verify that multi-paragraph search succeeds using chaining in the body."""
    doc = _test_doc
    text = doc.getText()
    cursor = text.createTextCursor()

    text.insertString(cursor, "First paragraph of the test.\nSecond paragraph of the test.", False)

    # Search with standard paragraph break
    found = _find_first_range(doc, "First paragraph of the test.\nSecond paragraph of the test.")
    assert found is not None
    assert "First paragraph" in found.getString()
    assert "Second paragraph" in found.getString()


@native_test
def test_search_exotic_space_in_cell_uno():
    """Verify that search finds exotic space matches inside a table cell."""
    doc = _test_doc
    text = doc.getText()
    tbl = doc.createInstance("com.sun.star.text.TextTable")
    tbl.initialize(2, 2)
    text.insertTextContent(text.createTextCursor(), tbl, False)

    # U+00A0 (NBSP) inside the cell
    cell = tbl.getCellByName("A1")
    cell.setString("Hello\u00a0World")

    # Search using a normal space
    found = _find_first_range(doc, "Hello World")
    assert found is not None
    assert found.getString() == "Hello\u00a0World"


@native_test
def test_search_multi_paragraph_in_frame_uno():
    """Verify that search finds multi-paragraph matches inside a text frame."""
    doc = _test_doc
    text = doc.getText()
    frame = doc.createInstance("com.sun.star.text.TextFrame")
    text.insertTextContent(text.createTextCursor(), frame, False)

    frame_text = frame.getText()
    fc = frame_text.createTextCursor()
    frame_text.insertString(fc, "Inside Frame Para 1.\nInside Frame Para 2.", False)

    found = _find_first_range(doc, "Inside Frame Para 1.\nInside Frame Para 2.")
    assert found is not None
    assert "Para 1" in found.getString()
    assert "Para 2" in found.getString()


@native_test
def test_search_real_paragraph_break_body_uno():
    """Verify that multi-paragraph chaining search succeeds with real paragraph breaks (multiple XText paragraphs)."""
    doc = _test_doc
    text = doc.getText()
    cursor = text.createTextCursor()
    cursor.gotoEnd(False)

    text.insertString(cursor, "First Paragraph (Real).", False)
    text.insertControlCharacter(cursor, 0, False)  # com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK
    text.insertString(cursor, "Second Paragraph (Real).", False)

    # Search with a newline representing a paragraph break
    found = _find_first_range(doc, "First Paragraph (Real).\nSecond Paragraph (Real).")
    assert found is not None
    assert "First Paragraph (Real)" in found.getString()
    assert "Second Paragraph (Real)" in found.getString()
