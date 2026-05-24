# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from plugin.scripting.editor_diagnostics import exception_traceback, failure_message


def test_exception_traceback_includes_frame():
    try:
        raise ValueError("probe failure")
    except ValueError as e:
        tb = exception_traceback(e)
    assert "ValueError: probe failure" in tb
    assert "test_exception_traceback_includes_frame" in tb


def test_failure_message_combines_summary_detail_and_trace():
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        msg = failure_message("Summary", detail="stderr line", exc=e)
    assert msg.startswith("Summary\n\n")
    assert "stderr line" in msg
    assert "RuntimeError: boom" in msg
