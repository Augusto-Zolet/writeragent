# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.doc.embeddings_indexer."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from plugin.doc import embeddings_cache, embeddings_indexer
from plugin.doc.embeddings_chunker import ParagraphChunk, content_hash


def test_file_is_stale_when_no_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert embeddings_indexer.file_is_stale(conn, "file:///a.odt", 100.0) is True


def test_file_is_stale_when_mtime_newer():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    embeddings_cache.ensure_host_schema(conn, embedding_model="m")
    conn.execute(
        "INSERT INTO chunks(doc_url, para_index, char_start, char_end, content_hash, last_indexed_at, embedding_model) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        ("file:///a.odt", 0, 0, 5, "h", 50.0, "m"),
    )
    conn.commit()
    assert embeddings_indexer.file_is_stale(conn, "file:///a.odt", 100.0) is True
    assert embeddings_indexer.file_is_stale(conn, "file:///a.odt", 40.0) is False


def test_diff_paragraph_rows_detects_change_and_delete():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    embeddings_cache.ensure_host_schema(conn, embedding_model="m")
    conn.execute(
        "INSERT INTO chunks(chunk_id, doc_url, para_index, char_start, char_end, content_hash, embedding_model) "
        "VALUES(1, ?, 0, 0, 4, ?, ?)",
        ("file:///a.odt", content_hash("old"), "m"),
    )
    conn.execute(
        "INSERT INTO chunks(chunk_id, doc_url, para_index, char_start, char_end, content_hash, embedding_model) "
        "VALUES(2, ?, 2, 0, 4, ?, ?)",
        ("file:///a.odt", content_hash("gone"), "m"),
    )
    conn.commit()

    chunks = [
        ParagraphChunk(
            doc_url="file:///a.odt",
            para_index=0,
            char_start=0,
            char_end=3,
            text="new",
            content_hash=content_hash("new"),
            file_mtime=1.0,
        ),
        ParagraphChunk(
            doc_url="file:///a.odt",
            para_index=1,
            char_start=0,
            char_end=3,
            text="added",
            content_hash=content_hash("added"),
            file_mtime=1.0,
        ),
    ]
    to_index, to_delete = embeddings_indexer.diff_paragraph_rows(conn, chunks)
    assert len(to_index) == 2
    assert to_index[0]["chunk_id"] == 1
    assert to_delete == [{"doc_url": "file:///a.odt", "para_index": 2}]


def test_needs_cold_rebuild_on_model_change():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    embeddings_cache.ensure_host_schema(conn, embedding_model="model-a")
    conn.execute(
        "INSERT INTO chunks(doc_url, para_index, char_start, char_end, content_hash, embedding_model) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        ("file:///a.odt", 0, 0, 1, "h", "model-a"),
    )
    conn.commit()
    assert embeddings_indexer.needs_cold_rebuild(conn, "model-b") is True
    assert embeddings_indexer.needs_cold_rebuild(conn, "model-a") is False


def test_enqueue_skipped_in_grep_mode():
    with patch("plugin.doc.embeddings_indexer.document_research_uses_embeddings", return_value=False):
        embeddings_indexer.enqueue_folder_index(MagicMock(), MagicMock(), MagicMock())


def test_mark_file_indexed_clears_stale_mtime():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    embeddings_cache.ensure_host_schema(conn, embedding_model="m")
    conn.execute(
        "INSERT INTO chunks(doc_url, para_index, char_start, char_end, content_hash, "
        "file_mtime, last_indexed_at, embedding_model) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        ("file:///a.odt", 0, 0, 5, "h", 90.0, 50.0, "m"),
    )
    conn.commit()
    assert embeddings_indexer.file_is_stale(conn, "file:///a.odt", 100.0) is True
    updated = embeddings_indexer.mark_file_indexed(conn, "file:///a.odt", 100.0, indexed_at=150.0)
    assert updated == 1
    state = embeddings_indexer.get_file_index_state(conn, "file:///a.odt")
    assert state["file_mtime"] == 100.0
    assert state["last_indexed_at"] == 150.0
    assert embeddings_indexer.file_is_stale(conn, "file:///a.odt", 100.0) is False


def test_refresh_marks_unchanged_file_after_mtime_bump(tmp_path):
    ctx = MagicMock()
    services = MagicMock()
    model = MagicMock()
    folder_key = "abc123"
    doc_url = "file:///a.odt"
    entry = {"url": doc_url, "path": "/tmp/a.odt", "modified": 200.0, "doc_type_guess": "writer"}
    chunk = ParagraphChunk(
        doc_url=doc_url,
        para_index=0,
        char_start=0,
        char_end=3,
        text="same",
        content_hash=content_hash("same"),
        file_mtime=200.0,
    )
    db_file = tmp_path / "index.db"

    with embeddings_cache.open_host_connection(db_file) as conn:
        embeddings_cache.ensure_host_schema(conn, embedding_model="m")
        conn.execute(
            "INSERT INTO chunks(doc_url, para_index, char_start, char_end, content_hash, "
            "file_mtime, last_indexed_at, embedding_model) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_url, 0, 0, 3, content_hash("same"), 100.0, 50.0, "m"),
        )
        conn.commit()

    with patch("plugin.doc.embeddings_indexer.get_embedding_model", return_value="m"):
        with patch("plugin.doc.embeddings_indexer.index_db_path", return_value=db_file):
            with patch("plugin.doc.embeddings_indexer.needs_cold_rebuild", return_value=False):
                with patch("plugin.doc.embeddings_indexer.list_indexable_sibling_files", return_value=([entry], None)):
                    with patch("plugin.doc.embeddings_indexer.extract_paragraph_chunks_from_file", return_value=[chunk]):
                        with patch("plugin.doc.embeddings_indexer.delete_paragraphs") as del_mock:
                            with patch("plugin.doc.embeddings_indexer.index_paragraphs") as idx_mock:
                                embeddings_indexer.refresh_folder_index_incremental(
                                    ctx, services, model, folder_key=folder_key
                                )
                                del_mock.assert_not_called()
                                idx_mock.assert_not_called()

    with embeddings_cache.open_host_connection(db_file) as conn:
        assert embeddings_indexer.file_is_stale(conn, doc_url, 200.0) is False
