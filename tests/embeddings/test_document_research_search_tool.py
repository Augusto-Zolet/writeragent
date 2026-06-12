# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plugin.embeddings.document_research_search_tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.embeddings.document_research_search_tool import SearchEmbeddings


def test_search_embeddings_disabled_returns_error():
    tool = SearchEmbeddings()
    ctx = MagicMock()
    ctx.ctx = MagicMock()
    with patch("plugin.framework.constants.document_research_uses_embeddings", return_value=False):
        result = tool.execute(ctx, query="budget figures")
    assert result["status"] == "error"
    assert result.get("code") == "EMBEDDINGS_CACHE_DISABLED"
