# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Embeddings module — Settings schema for per-folder semantic search cache."""

from plugin.framework.module_base import ModuleBase


class EmbeddingsModule(ModuleBase):
    """Config-only module; indexing and search tools live under plugin.doc."""
