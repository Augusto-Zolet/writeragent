# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for OpenRouter catalog merge used by ``make openrouter-catalog``."""

from __future__ import annotations

from plugin.framework.constants import ModelCapability
from plugin.framework.deal_shim import DEAL_MAX_SHAPE_DIM
from scripts.sync_orca_openrouter_catalog import merge_defaults_for_openrouter


def test_merge_defaults_survives_large_catalog_and_free_alias() -> None:
    """Live Orca catalogs exceed DEAL_MAX_SHAPE_DIM; dict_keys used to PreContractError."""
    slim_by_id: dict[str, dict[str, object]] = {
        f"vendor/model-{i}": {"id": f"vendor/model-{i}", "context_length": 100}
        for i in range(DEAL_MAX_SHAPE_DIM + 50)
    }
    slim_by_id["openai/gpt-oss-120b"] = {
        "id": "openai/gpt-oss-120b",
        "context_length": 131072,
    }
    defaults = [
        {
            "display_name": "Free Models (Auto)",
            "capability": ModelCapability.CHAT,
            "context_length": 131072,
            "ids": {"openrouter": "openrouter/free"},
        },
        {
            "display_name": "GPT-OSS 120B",
            "capability": ModelCapability.CHAT,
            "context_length": 1,
            "ids": {"openrouter": "openai/gpt-oss-120b:nitro"},
        },
    ]
    merged = merge_defaults_for_openrouter(defaults, slim_by_id, strict=True)
    assert merged[0]["ids"]["openrouter"] == "openrouter/free"
    assert merged[0]["context_length"] == 131072
    assert merged[1]["context_length"] == 131072
