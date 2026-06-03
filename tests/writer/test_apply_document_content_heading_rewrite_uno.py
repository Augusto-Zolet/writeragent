# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Regression test: replacing text inside a heading paragraph with inline HTML (e.g. a
# <span>) used to silently downgrade the paragraph to a normal one, losing the heading
# level (and its outline semantics). The fix preserves the target paragraph style for
# inline-only content and inserts the fragment raw, so the StarWriter HTML filter does
# not wrap it in an extra <p>.
import uno  # noqa: F401

from plugin.testing_runner import native_test, setup, teardown
from plugin.writer.content import ApplyDocumentContent
from plugin.tests.testing_utils import TestingFactory

_test_doc = None
_test_ctx = None

_HEADING_TEXT = "4.1.1 Engine selection"


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


def _doc_with_heading3():
    doc = _test_doc
    text = doc.getText()
    cur = text.createTextCursor()
    cur.gotoStart(False)
    cur.gotoEnd(True)
    cur.setString("")
    cur.gotoStart(False)
    text.insertString(cur, _HEADING_TEXT, False)
    pcur = text.createTextCursorByRange(text.getStart())
    pcur.gotoEnd(True)
    pcur.setPropertyValue("ParaStyleName", "Heading 3")
    chk = text.createTextCursorByRange(text.getStart())
    assert chk.getPropertyValue("ParaStyleName") == "Heading 3"
    return doc, text


def _para_style_at_start(text):
    chk = text.createTextCursorByRange(text.getStart())
    return chk.getPropertyValue("ParaStyleName")


@native_test
def test_apply_document_content_preserves_heading_level_span_uno():
    """Replacing heading text with inline <span> must not demote the paragraph."""
    doc, text = _doc_with_heading3()
    tool_ctx = TestingFactory.create_context(doc=doc, ctx=_test_ctx, env="native")
    res = ApplyDocumentContent().execute(
        tool_ctx,
        content=['<span style="background: transparent">%s</span>' % _HEADING_TEXT],
        old_content=_HEADING_TEXT,
        target="search",
    )
    assert res.get("status") == "ok", f"apply_document_content failed: {res}"
    assert _para_style_at_start(text) == "Heading 3", \
        "apply_document_content demoted the heading to '%s'" % _para_style_at_start(text)


@native_test
def test_apply_document_content_preserves_heading_level_b_uno():
    """Replacing heading text with inline <b> must not demote the paragraph."""
    doc, text = _doc_with_heading3()
    tool_ctx = TestingFactory.create_context(doc=doc, ctx=_test_ctx, env="native")
    res = ApplyDocumentContent().execute(
        tool_ctx,
        content=["<b>%s</b>" % _HEADING_TEXT],
        old_content=_HEADING_TEXT,
        target="search",
    )
    assert res.get("status") == "ok", f"apply_document_content failed: {res}"
    assert _para_style_at_start(text) == "Heading 3", \
        "apply_document_content demoted the heading to '%s'" % _para_style_at_start(text)


@native_test
def test_apply_document_content_block_markup_changes_heading_level_uno():
    """Block-level HTML (e.g. <h2>) must apply its own paragraph style, not preserve Heading 3."""
    doc, text = _doc_with_heading3()
    tool_ctx = TestingFactory.create_context(doc=doc, ctx=_test_ctx, env="native")
    res = ApplyDocumentContent().execute(
        tool_ctx,
        content=["<h2>New title</h2>"],
        old_content=_HEADING_TEXT,
        target="search",
    )
    assert res.get("status") == "ok", f"apply_document_content failed: {res}"
    para_style = _para_style_at_start(text)
    assert para_style == "Heading 2", \
        "block markup should set Heading 2, got '%s'" % para_style
