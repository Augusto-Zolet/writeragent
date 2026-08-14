# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for plugin.doc.doc_type."""

from plugin.doc.doc_type import DocumentType, doc_type_label_for_enum, doc_type_title_for_label


def test_doc_type_label_and_title_helpers():
    assert doc_type_label_for_enum(DocumentType.WRITER) == "writer"
    assert doc_type_label_for_enum(DocumentType.CALC) == "calc"
    assert doc_type_label_for_enum(DocumentType.DRAW) == "draw"
    # ToolContext / sidebar: Impress stays distinct for PresentationDocument uno_services.
    assert doc_type_label_for_enum(DocumentType.IMPRESS) == "impress"
    # Document research / path-family labels collapse Draw+Impress to "draw".
    assert doc_type_label_for_enum(DocumentType.IMPRESS, impress_as_draw=True) == "draw"
    assert doc_type_label_for_enum(DocumentType.DRAW, impress_as_draw=True) == "draw"
    assert doc_type_label_for_enum(DocumentType.UNKNOWN) == "unknown"
    assert doc_type_title_for_label("impress") == "Draw"
    assert doc_type_title_for_label("draw") == "Draw"
    assert doc_type_title_for_label("calc") == "Calc"
