# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for Monaco editor child stderr drain (tail buffer for failure dialogs)."""

from __future__ import annotations

import os
import threading
from unittest.mock import patch

from plugin.scripting.editor_bridge import PersistentEditor


class _FakeProc:
    """Minimal process stand-in for stderr drain tests (no MagicMock fileno quirks)."""

    def __init__(self, stderr: object) -> None:
        self.stderr = stderr
        self.stdout = None
        self.stdin = None
        self._exit_code: int | None = None

    def poll(self) -> int | None:
        return self._exit_code


def test_stderr_drain_preserves_tail_for_failure_dialogs():
    """Drain loop fills the ring buffer used by read_stderr_tail().

    Release bundles strip log.debug calls (see scripts/strip_code.py), so this
    test asserts tail behavior only — the part that survives make release.
    """
    editor = PersistentEditor()
    read_fd, write_fd = os.pipe()
    stderr = os.fdopen(read_fd, "rb")
    write_handle = os.fdopen(write_fd, "wb")
    proc = _FakeProc(stderr)

    drain_thread: threading.Thread | None = None

    def start_thread(fn, **kw):
        nonlocal drain_thread
        drain_thread = threading.Thread(target=fn, daemon=True, name=kw.get("name", "t"))
        drain_thread.start()
        return drain_thread

    with patch("plugin.scripting.editor_bridge.run_in_background", side_effect=start_thread):
        editor.start(proc)  # type: ignore[arg-type]
        write_handle.write(b"line one\nline two\n")
        write_handle.flush()
        write_handle.write(b"final line\n")
        write_handle.flush()
        write_handle.close()
        proc._exit_code = 0
        assert drain_thread is not None
        drain_thread.join(timeout=3.0)
        assert not drain_thread.is_alive(), "stderr drain thread did not finish"

    tail = editor.read_stderr_tail()
    assert "line one" in tail
    assert "line two" in tail
    assert "final line" in tail


def test_append_stderr_line_ring_buffer():
    editor = PersistentEditor()
    editor._stderr_tail_max_chars = 12
    editor._append_stderr_line("aaaa")
    editor._append_stderr_line("bbbb")
    editor._append_stderr_line("cccc")
    tail = editor.read_stderr_tail()
    assert "aaaa" not in tail
    assert "bbbb" in tail
    assert "cccc" in tail
