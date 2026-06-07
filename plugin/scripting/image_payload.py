# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers for matplotlib ``__wa_payload__: "image"`` envelopes (Phase A Viz)."""

from __future__ import annotations

import os
import tempfile
from typing import Any


def image_payload_suffix(payload: dict[str, Any]) -> str:
    """Return a temp-file suffix for *payload* (``.svg`` or ``.png``)."""
    fmt = str(payload.get("format") or "png").lower()
    return ".svg" if fmt == "svg" else ".png"


def write_image_payload_to_temp(payload: dict[str, Any]) -> str:
    """Write image bytes from *payload* to a persistent temp file; return absolute path."""
    suffix = image_payload_suffix(payload)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(payload["data"])
        return os.path.abspath(tmp.name)
