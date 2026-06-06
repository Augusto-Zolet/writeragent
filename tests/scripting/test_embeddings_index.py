# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.scripting.embeddings_index."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from plugin.scripting import embeddings_index


@pytest.fixture(autouse=True)
def clear_model_cache():
    embeddings_index._MODEL_CACHE.clear()
    yield
    embeddings_index._MODEL_CACHE.clear()


def test_embed_texts_empty_input():
    result = embeddings_index.embed_texts("all-MiniLM-L6-v2", [])
    assert result == {"model": "all-MiniLM-L6-v2", "dim": 0, "vectors": [], "indices": []}


def test_embed_texts_skips_blank_strings():
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [np.array([1.0, 0.0], dtype=np.float32), np.array([0.0, 1.0], dtype=np.float32)]

    with patch.object(embeddings_index, "_get_embedder", return_value=mock_embedder):
        result = embeddings_index.embed_texts("all-MiniLM-L6-v2", ["  hello  ", "", "world", "   "])

    assert result["indices"] == [0, 2]
    assert result["dim"] == 2
    assert len(result["vectors"]) == 2
    mock_embedder.encode.assert_called_once_with(["hello", "world"], convert_to_tensor=False, show_progress_bar=False)


def test_embed_texts_normalizes_vectors():
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [np.array([3.0, 4.0], dtype=np.float32)]

    with patch.object(embeddings_index, "_get_embedder", return_value=mock_embedder):
        result = embeddings_index.embed_texts("all-MiniLM-L6-v2", ["text"], normalize=True)

    vec = np.array(result["vectors"][0], dtype=np.float32)
    assert pytest.approx(float(np.linalg.norm(vec)), rel=1e-5) == 1.0


def test_embed_texts_reuses_cached_model():
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [np.array([1.0, 0.0], dtype=np.float32)]
    mock_ctor = MagicMock(return_value=mock_embedder)
    fake_mod = MagicMock()
    fake_mod.SentenceTransformer = mock_ctor

    with patch.dict(sys.modules, {"sentence_transformers": fake_mod}):
        embeddings_index.embed_texts("all-MiniLM-L6-v2", ["a"])
        embeddings_index.embed_texts("all-MiniLM-L6-v2", ["b"])

    mock_ctor.assert_called_once_with("all-MiniLM-L6-v2")
    assert mock_embedder.encode.call_count == 2


def test_embed_texts_requires_model_name():
    with pytest.raises(ValueError, match="model name"):
        embeddings_index.embed_texts("", ["text"])


def test_index_paragraphs_blob_fallback(tmp_path):
    db_path = tmp_path / "index.db"
    import sqlite3

    from plugin.doc.embeddings_cache import ensure_host_schema

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_host_schema(conn, embedding_model="all-MiniLM-L6-v2")

    mock_embedder = MagicMock()
    mock_embedder.encode.side_effect = lambda texts, **_: [__import__("numpy").array([1.0, 0.0], dtype=__import__("numpy").float32) for _ in texts]

    rows = [
        {
            "doc_url": "file:///a.odt",
            "para_index": 0,
            "char_start": 0,
            "char_end": 4,
            "content_hash": "abc",
            "text": "hello",
            "file_mtime": 1.0,
        }
    ]

    with patch.object(embeddings_index, "_SQLITE_VEC_AVAILABLE", False):
        with patch.object(embeddings_index, "_get_embedder", return_value=mock_embedder):
            result = embeddings_index.index_paragraphs(str(db_path), "all-MiniLM-L6-v2", rows)

    assert result["indexed"] == 1
    assert result["storage_backend"] == "blob_numpy"

    with patch.object(embeddings_index, "_SQLITE_VEC_AVAILABLE", False):
        with patch.object(embeddings_index, "_get_embedder", return_value=mock_embedder):
            search = embeddings_index.knn_search(str(db_path), "hello", 1, model_name="all-MiniLM-L6-v2")

    assert len(search["hits"]) == 1
    assert search["hits"][0]["doc_url"] == "file:///a.odt"
