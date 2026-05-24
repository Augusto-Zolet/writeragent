# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for editor stdin/stdout JSON protocol."""

from __future__ import annotations

import io
import json
import struct

import pytest

from plugin.scripting.editor_protocol import read_message, write_message


def test_roundtrip_simple():
    buf = io.BytesIO()
    write_message(buf, {"type": "ready", "version": 1})
    buf.seek(0)
    msg = read_message(buf)
    assert msg == {"type": "ready", "version": 1}


def test_roundtrip_unicode():
    buf = io.BytesIO()
    write_message(buf, {"type": "load", "code": "result = 'ü'"})
    buf.seek(0)
    assert read_message(buf)["code"] == "result = 'ü'"


def test_eof_returns_none():
    buf = io.BytesIO()
    assert read_message(buf) is None


def test_truncated_payload_returns_none():
    buf = io.BytesIO()
    buf.write(struct.pack("!I", 100))
    buf.write(b"short")
    buf.seek(0)
    assert read_message(buf) is None


def test_invalid_size_raises():
    buf = io.BytesIO()
    buf.write(struct.pack("!I", 32 * 1024 * 1024))
    buf.seek(0)
    with pytest.raises(ValueError, match="Invalid editor message size"):
        read_message(buf)
