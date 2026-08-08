from types import SimpleNamespace

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc
from plugin.doc.document_helpers import DocumentService
from plugin.writer.specialized.bookmarks import BookmarkService


def _setup_headings(doc):
    text = doc.getText()
    cursor = text.createTextCursor()

    # 0: Heading 1
    text.insertString(cursor, "Main Heading", False)
    cursor.setPropertyValue("ParaStyleName", "Heading 1")
    text.insertControlCharacter(cursor, 0, False)

    # 1: Paragraph
    text.insertString(cursor, "A simple paragraph.", False)
    cursor.setPropertyValue("ParaStyleName", "Standard")
    text.insertControlCharacter(cursor, 0, False)

    # 2: Heading 2
    text.insertString(cursor, "Sub Heading", False)
    cursor.setPropertyValue("ParaStyleName", "Heading 2")
    text.insertControlCharacter(cursor, 0, False)


@native_test
@with_native_doc("writer")
def test_ensure_heading_bookmarks_and_map(ctx, doc):
    _setup_headings(doc)
    doc_svc = DocumentService()
    bookmark_svc = BookmarkService(SimpleNamespace(document=doc_svc))

    # Initially no bookmarks
    bms = doc.getBookmarks().getElementNames()
    assert len([b for b in bms if b.startswith("_mcp_")]) == 0

    # Ensure bookmarks
    bookmark_map = bookmark_svc.ensure_heading_bookmarks(doc)

    # We have 2 headings (index 0 and 2)
    assert len(bookmark_map) == 2
    assert 0 in bookmark_map
    assert 2 in bookmark_map

    # Verify in document
    bms = doc.getBookmarks().getElementNames()
    mcp_bms = [b for b in bms if b.startswith("_mcp_")]
    assert len(mcp_bms) == 2

    # Verify map retrieval
    retrieved_map = bookmark_svc.get_mcp_bookmark_map(doc)
    assert retrieved_map == bookmark_map


@native_test
@with_native_doc("writer")
def test_find_nearest_heading_bookmark(ctx, doc):
    _setup_headings(doc)
    doc_svc = DocumentService()
    bookmark_svc = BookmarkService(SimpleNamespace(document=doc_svc))

    bookmark_map = bookmark_svc.ensure_heading_bookmarks(doc)

    # Nearest heading before or at index 1 is index 0
    res = bookmark_svc.find_nearest_heading_bookmark(1, bookmark_map)
    assert res is not None
    assert res["heading_para_index"] == 0
    assert res["bookmark"] == bookmark_map[0]

    # Nearest heading before or at index 2 is index 2
    res = bookmark_svc.find_nearest_heading_bookmark(2, bookmark_map)
    assert res is not None
    assert res["heading_para_index"] == 2
    assert res["bookmark"] == bookmark_map[2]


@native_test
@with_native_doc("writer")
def test_cleanup_mcp_bookmarks(ctx, doc):
    _setup_headings(doc)
    doc_svc = DocumentService()
    bookmark_svc = BookmarkService(SimpleNamespace(document=doc_svc))

    # Ensure we have some bookmarks
    bookmark_svc.ensure_heading_bookmarks(doc)

    # Clean them up
    removed_count = bookmark_svc.cleanup_mcp_bookmarks(doc)
    assert removed_count == 2

    # Verify they are gone from document
    bms = doc.getBookmarks().getElementNames()
    mcp_bms = [b for b in bms if b.startswith("_mcp_")]
    assert len(mcp_bms) == 0

    # Verify map is empty on next read
    empty_map = bookmark_svc.get_mcp_bookmark_map(doc)
    assert len(empty_map) == 0
