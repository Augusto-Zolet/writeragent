# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for editor child ``closed`` lifecycle messaging."""

from __future__ import annotations

from plugin.scripting import editor_main as em


def _reset_closed_state() -> None:
    em._closed_sent = False
    em._shutting_down = False


def test_send_closed_once_writes_single_message(monkeypatch):
    _reset_closed_state()
    messages: list[dict] = []
    monkeypatch.setattr(em, "_write_parent", messages.append)

    em._send_closed_once()
    em._send_closed_once()

    assert messages == [{"type": "closed"}]
    assert em._closed_sent is True
    assert em._shutting_down is True


def test_notify_cancel_sends_closed_once(monkeypatch):
    _reset_closed_state()
    messages: list[dict] = []
    monkeypatch.setattr(em, "_write_parent", messages.append)

    api = em.MonacoEditorApi()
    api._window = object()
    api.notify_cancel()
    api.notify_cancel()

    assert messages == [{"type": "closed"}]
