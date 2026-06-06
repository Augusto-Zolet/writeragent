# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.doc.embeddings_chunker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.doc import embeddings_chunker


def test_content_hash_stable():
    assert embeddings_chunker.content_hash("  hello  ") == embeddings_chunker.content_hash("hello")
    assert embeddings_chunker.content_hash("hello") != embeddings_chunker.content_hash("world")


def test_writer_paragraph_chunks_skips_blank():
    services = MagicMock()
    para_a = MagicMock()
    para_a.supportsService.return_value = True
    para_a.getString.return_value = "First paragraph"
    para_b = MagicMock()
    para_b.supportsService.return_value = True
    para_b.getString.return_value = "   "
    services.document.get_paragraph_ranges.return_value = [para_a, para_b]

    chunks = embeddings_chunker._writer_paragraph_chunks(
        MagicMock(),
        services,
        doc_url="file:///a.odt",
        doc_path="/a.odt",
        file_mtime=1.0,
    )
    assert len(chunks) == 1
    assert chunks[0].para_index == 0
    assert chunks[0].text == "First paragraph"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len("First paragraph")


def test_extract_paragraph_chunks_from_file_skips_non_writer():
    entry = {
        "path": "/x.ods",
        "url": "file:///x.ods",
        "doc_type_guess": "calc",
        "modified": 1.0,
    }
    assert embeddings_chunker.extract_paragraph_chunks_from_file(MagicMock(), MagicMock(), entry) == []


@patch("plugin.doc.embeddings_chunker.close_document_research_document")
@patch("plugin.doc.embeddings_chunker.open_document_for_read")
def test_extract_paragraph_chunks_from_file_writer(mock_open, mock_close):
    model = MagicMock()
    mock_open.return_value = (model, "writer", None, True)
    services = MagicMock()
    para = MagicMock()
    para.supportsService.return_value = True
    para.getString.return_value = "Body text"
    services.document.get_paragraph_ranges.return_value = [para]
    entry = {
        "path": "/doc.odt",
        "url": "file:///doc.odt",
        "doc_type_guess": "writer",
        "modified": 2.0,
    }
    chunks = embeddings_chunker.extract_paragraph_chunks_from_file(MagicMock(), services, entry)
    assert len(chunks) == 1
    mock_close.assert_called_once_with(model, opened_for_document_research=True)
