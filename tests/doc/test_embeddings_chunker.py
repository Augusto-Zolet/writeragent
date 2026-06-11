# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.doc.embeddings_chunker (re-exports embeddings_fs)."""

from __future__ import annotations

from plugin.doc import embeddings_chunker


def test_content_hash_stable():
    assert embeddings_chunker.content_hash("  hello  ") == embeddings_chunker.content_hash("hello")
    assert embeddings_chunker.content_hash("hello") != embeddings_chunker.content_hash("world")
