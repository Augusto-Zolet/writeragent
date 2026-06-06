# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.doc.embeddings_cache."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from plugin.doc import embeddings_cache


def test_folder_corpus_key_stable_and_normalized():
    a = embeddings_cache.folder_corpus_key("/tmp/foo/bar")
    b = embeddings_cache.folder_corpus_key("/tmp/foo/bar/")
    c = embeddings_cache.folder_corpus_key("/tmp/foo/../foo/bar")
    assert a == b == c
    assert len(a) == 64


def test_index_db_path_under_profile(tmp_path):
    ctx = MagicMock()
    with patch("plugin.doc.embeddings_cache.user_config_dir", return_value=str(tmp_path)):
        path = embeddings_cache.index_db_path(ctx, "abc123")
    assert path == tmp_path / "writeragent_embeddings" / "abc123" / "index.db"
    assert path.parent.is_dir()


def test_ensure_host_schema_idempotent(tmp_path):
    db_path = tmp_path / "index.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        embeddings_cache.ensure_host_schema(conn, embedding_model="all-MiniLM-L6-v2", dim=384)
        embeddings_cache.ensure_host_schema(conn, embedding_model="all-MiniLM-L6-v2", dim=384)
        meta = embeddings_cache.read_corpus_meta(conn)
        assert meta["schema_version"] == embeddings_cache.SCHEMA_VERSION
        assert meta["embedding_model"] == "all-MiniLM-L6-v2"
        assert meta["dim"] == "384"
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "chunks" in tables
        assert "corpus_meta" in tables


def test_index_is_empty_missing_and_populated(tmp_path):
    missing = tmp_path / "missing.db"
    assert embeddings_cache.index_is_empty(missing) is True

    db_path = tmp_path / "index.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        embeddings_cache.ensure_host_schema(conn, embedding_model="m")
    assert embeddings_cache.index_is_empty(db_path) is True

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO chunks(doc_url, para_index, char_start, char_end, content_hash, embedding_model) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            ("file:///a.odt", 0, 0, 5, "h", "m"),
        )
        conn.commit()
    assert embeddings_cache.index_is_empty(db_path) is False


def test_resolve_index_context_no_listing_root():
    ctx = MagicMock()
    model = MagicMock()
    with patch("plugin.doc.embeddings_cache.resolve_folder_for_active_doc", return_value=None):
        key, path, err = embeddings_cache.resolve_index_context(ctx, model)
    assert key is None
    assert path is None
    assert "Save the document" in err


def test_resolve_index_context_ok(tmp_path):
    ctx = MagicMock()
    model = MagicMock()
    listing = str(tmp_path / "project")
    Path(listing).mkdir()
    with patch("plugin.doc.embeddings_cache.resolve_folder_for_active_doc", return_value=listing):
        with patch("plugin.doc.embeddings_cache.user_config_dir", return_value=str(tmp_path / "profile")):
            key, path, root = embeddings_cache.resolve_index_context(ctx, model)
    assert root == listing
    assert key == embeddings_cache.folder_corpus_key(listing)
    assert path.name == "index.db"


def test_model_matches_index():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    embeddings_cache.ensure_host_schema(conn, embedding_model="model-a")
    assert embeddings_cache.model_matches_index(conn, "model-a") is True
    assert embeddings_cache.model_matches_index(conn, "model-b") is False
