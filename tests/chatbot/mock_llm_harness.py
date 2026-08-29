# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process mock-LLM config helper for native sidebar tests (not shipped)."""

from __future__ import annotations

from typing import Any


def mock_config(config: Any, **flags: Any) -> Any:
    """Mutate a ``MockLLMConfig`` (or similar) in place and return it."""
    for key, value in flags.items():
        setattr(config, key, value)
    return config
