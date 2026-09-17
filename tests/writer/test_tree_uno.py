from types import SimpleNamespace

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc


@native_test
@with_native_doc("writer")
def test_tree_service_basic(ctx, doc):
    from plugin.writer.tree import TreeService
    from plugin.writer.specialized.bookmarks import BookmarkService
    from plugin.framework.event_bus import EventBus
    from plugin.doc.document_helpers import DocumentService
    
    # Setup doc content with headings
    text = doc.getText()
    cursor = text.createTextCursor()

    # H1
    text.insertString(cursor, "H1", False)
    cursor.setPropertyValue("ParaStyleName", "Heading 1")
    text.insertControlCharacter(cursor, 0, False)

    # P1
    text.insertString(cursor, "P1", False)
    text.insertControlCharacter(cursor, 0, False)

    # H1.1
    text.insertString(cursor, "H1.1", False)
    cursor.setPropertyValue("ParaStyleName", "Heading 2")
    text.insertControlCharacter(cursor, 0, False)

    events = EventBus()
    doc_svc = DocumentService()
    services = SimpleNamespace()
    services.document = doc_svc
    services.events = events
    services.writer_bookmarks = BookmarkService()
    services.writer_tree = TreeService(services)
    tree_svc = services.writer_tree

    # 1. Test build_heading_tree from TreeService natively
    tree = tree_svc.build_heading_tree(doc)
    assert tree is not None, "TreeService.build_heading_tree returned None"
    assert "children" in tree and len(tree["children"]) >= 1

    h1 = tree["children"][0]
    assert h1["text"] == "H1", "First child should be H1"

    # 2. Test resolve_writer_locator from TreeService natively
    res = tree_svc.resolve_writer_locator(doc, "heading", "1.1")
    assert res is not None and res.get("para_index") == 2, f"Failed to resolve heading:1.1, got {res}"

    res = tree_svc.resolve_writer_locator(doc, "heading_text", "H1.1")
    assert res is not None and res.get("para_index") == 2, f"Failed to resolve heading_text:H1.1, got {res}"


def _heading_texts(tree):
    return [child["text"] for child in tree.get("children", [])]


def _tree_svc_on_bus():
    from types import SimpleNamespace

    from plugin.doc.document_helpers import DocumentService
    from plugin.framework.event_bus import get_event_bus
    from plugin.writer.specialized.bookmarks import BookmarkService
    from plugin.writer.tree import TreeService

    events = get_event_bus()
    services = SimpleNamespace()
    services.document = DocumentService()
    services.events = events
    services.writer_bookmarks = BookmarkService()
    tree_svc = TreeService(services)
    return tree_svc, events


def _insert_heading(doc, text, style="Heading 1"):
    cursor = doc.getText().createTextCursor()
    cursor.gotoEnd(False)
    body = doc.getText()
    body.insertControlCharacter(cursor, 0, False)
    body.insertString(cursor, text, False)
    cursor.setPropertyValue("ParaStyleName", style)


def _drain_ui(ctx):
    from plugin.framework.uno_context import get_toolkit

    toolkit = get_toolkit(ctx)
    if toolkit is not None:
        toolkit.processEventsToIdle()


@native_test
@with_native_doc("writer")
def test_tree_cache_two_wrappers_one_entry(ctx, doc):
    from plugin.framework.uno_context import get_runtime_uid

    _insert_heading(doc, "Shared")
    other = doc.getCurrentController().getModel()
    assert get_runtime_uid(doc) == get_runtime_uid(other)
    assert get_runtime_uid(doc)

    tree_svc, events = _tree_svc_on_bus()
    try:
        key_a = tree_svc._doc_svc.doc_key(doc)
        key_b = tree_svc._doc_svc.doc_key(other)
        assert key_a == key_b
        tree_a = tree_svc.build_heading_tree(doc)
        tree_b = tree_svc.build_heading_tree(other)
        assert tree_a is tree_b
        assert len(tree_svc._tree_cache) == 1
        assert "Shared" in _heading_texts(tree_a)
    finally:
        events.unsubscribe("document:cache_invalidated", tree_svc._on_cache_invalidated)


@native_test
@with_native_doc("writer")
def test_tree_cache_external_edit_invalidates(ctx, doc):
    _insert_heading(doc, "Before")
    tree_svc, events = _tree_svc_on_bus()
    try:
        first = tree_svc.build_heading_tree(doc)
        assert "Before" in _heading_texts(first)
        assert "After" not in _heading_texts(first)
        cached = tree_svc.build_heading_tree(doc)
        assert cached is first

        _insert_heading(doc, "After")
        _drain_ui(ctx)

        second = tree_svc.build_heading_tree(doc)
        assert second is not first
        assert "After" in _heading_texts(second)
    finally:
        events.unsubscribe("document:cache_invalidated", tree_svc._on_cache_invalidated)


@native_test
def test_tree_cache_two_docs_do_not_share_entry(ctx):
    from plugin.tests.testing_utils import TestingFactory

    tree_svc, events = _tree_svc_on_bus()
    try:
        with TestingFactory.native_doc(ctx, doc_type="writer", hidden=True, reuse=False) as doc_a:
            with TestingFactory.native_doc(ctx, doc_type="writer", hidden=True, reuse=False) as doc_b:
                _insert_heading(doc_a, "DocA")
                _insert_heading(doc_b, "DocB")
                tree_a = tree_svc.build_heading_tree(doc_a)
                tree_b = tree_svc.build_heading_tree(doc_b)
                assert tree_a is not tree_b
                assert "DocA" in _heading_texts(tree_a)
                assert "DocB" not in _heading_texts(tree_a)
                assert "DocB" in _heading_texts(tree_b)
                assert "DocA" not in _heading_texts(tree_b)
                assert tree_svc._doc_svc.doc_key(doc_a) != tree_svc._doc_svc.doc_key(doc_b)
    finally:
        events.unsubscribe("document:cache_invalidated", tree_svc._on_cache_invalidated)
