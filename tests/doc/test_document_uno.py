
from plugin.doc.document_helpers import (
    normalize_linebreaks,
    _normalize_doc_url,
    _inject_markers_into_excerpt
)

def test_normalize_linebreaks():
    # Basic and CRLF/CR/LF variants
    assert normalize_linebreaks("hello\r\nworld") == "hello\nworld"
    assert normalize_linebreaks("hello\n\rworld") == "hello\nworld"
    assert normalize_linebreaks("hello\rworld") == "hello\nworld"
    assert normalize_linebreaks("Line 1\nLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\r\nLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\rLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\n\rLine 2") == "Line 1\nLine 2"
    # Mixed and multiple
    assert normalize_linebreaks("A\r\nB\rC\n\rD\nE") == "A\nB\nC\nD\nE"
    assert normalize_linebreaks("\r\n\r\n") == "\n\n"
    assert normalize_linebreaks("\n\r\n\r") == "\n\n"
    assert normalize_linebreaks("\r\r") == "\n\n"
    # Edge cases
    assert normalize_linebreaks("") == ""
    assert normalize_linebreaks(None) == ""

def test_normalize_doc_url():
    assert _normalize_doc_url("file:///test/") == "file:///test"
    assert _normalize_doc_url("file:///test") == "file:///test"
    assert _normalize_doc_url("") == ""
    assert _normalize_doc_url(None) == ""

def test_inject_markers_into_excerpt():
    text = "0123456789"
    # Excerpt covers 0-10, selection is 2-5
    out = _inject_markers_into_excerpt(text, 0, 10, 2, 5, "PRE", "SUF")
    assert out == "PRE01[SELECTION_START]234[SELECTION_END]56789SUF"

    # Excerpt covers 10-20, selection is 5-8 (outside excerpt)
    out = _inject_markers_into_excerpt(text, 10, 20, 5, 8, "PRE", "SUF")
    assert out == "PRE0123456789SUF"

def test_is_document_disposed():
    from plugin.doc.document_helpers import is_document_disposed

    assert is_document_disposed(None) is True

    try:
        from com.sun.star.lang import DisposedException
        disposed_exc = DisposedException("Document disposed")
    except ImportError:
        disposed_exc = Exception("Mock disposed")

    class MockDisposedDoc:
        def getImplementationName(self):
            raise disposed_exc

    class MockValidDoc:
        def getImplementationName(self):
            return "SwXTextDocument"

    assert is_document_disposed(MockDisposedDoc()) is True
    assert is_document_disposed(MockValidDoc()) is False


