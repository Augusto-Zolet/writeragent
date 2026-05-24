# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Format editor failures with full tracebacks for user-visible dialogs."""

from __future__ import annotations

import traceback


def exception_traceback(exc: BaseException) -> str:
    """Full traceback string for *exc*."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def failure_detail(*, detail: str = "", exc: BaseException | None = None) -> str:
    """Combine subprocess stderr, probe output, and/or an exception traceback."""
    chunks: list[str] = []
    if detail.strip():
        chunks.append(detail.strip())
    if exc is not None:
        chunks.append(exception_traceback(exc).rstrip())
    return "\n\n".join(chunks)


def failure_message(summary: str, *, detail: str = "", exc: BaseException | None = None) -> str:
    """Build a msgbox body: *summary* plus optional detail/traceback blocks."""
    body = failure_detail(detail=detail, exc=exc)
    if body:
        return f"{summary}\n\n{body}"
    return summary
