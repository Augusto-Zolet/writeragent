# WriterAgent - tests for document user-defined properties

from __future__ import annotations

from plugin.doc.udprops import get_document_property


def test_get_document_property_missing_api_returns_default():
    class _Model:
        pass

    assert get_document_property(_Model(), "WriterAgentSessionID", default="x") == "x"
