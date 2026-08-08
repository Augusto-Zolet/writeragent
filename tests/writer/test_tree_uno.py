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
    services.writer_bookmarks = BookmarkService(services)
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
