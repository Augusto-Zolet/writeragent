# WriterAgent - Tests for MainThreadToken type-state
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the compile-time MainThreadToken type-state mechanism."""

import threading
from unittest.mock import MagicMock
import pytest

from plugin.framework.thread_token import require_main_thread
from plugin.framework import thread_guard as tg


def test_require_main_thread_on_main():
    token = require_main_thread()
    assert token is not None
    assert isinstance(token, object)


def test_require_main_thread_raises_off_main(monkeypatch):
    fake_bg = MagicMock()
    fake_bg.name = "worker-token"
    monkeypatch.setattr(threading, "current_thread", lambda: fake_bg)
    monkeypatch.setattr(tg, "on_main_thread", lambda: False)
    was = tg.GUARD_ON
    tg.GUARD_ON = True
    try:
        with pytest.raises(RuntimeError) as exc_info:
            require_main_thread()
        assert "UNO thread violation" in str(exc_info.value)
    finally:
        tg.GUARD_ON = was
