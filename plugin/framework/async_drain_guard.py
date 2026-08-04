# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Main-Thread Async Event Loop Sentry.

Enforces single-ownership of main-thread UI event pumping to prevent
harmful nested event-loop reentrancy (e.g. recursive processEventsToIdle calls).
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

log = logging.getLogger("writeragent.framework.async_drain_guard")

_drain_lock = threading.Lock()
_active_owner_name: str | None = None
_drain_depth: int = 0
_suppressed_vcl_count: int = 0


class NestedDrainOwnerError(RuntimeError):
    """Raised when a second drain owner attempts to start while another is active."""


@contextmanager
def drain_owner_sentry(owner_name: str) -> Generator[None, None, None]:
    """Sentry context manager ensuring single-ownership of main-thread UI event pumping."""
    global _active_owner_name, _drain_depth
    with _drain_lock:
        if _active_owner_name is not None and _active_owner_name != owner_name:
            msg = f"[SENTRY VIOLATION] Nested UI drain attempted by {owner_name!r} while {_active_owner_name!r} owns event loop"
            log.warning(msg)
            raise NestedDrainOwnerError(msg)
        previous_owner = _active_owner_name
        _active_owner_name = owner_name
        _drain_depth += 1

    try:
        yield
    finally:
        with _drain_lock:
            _drain_depth -= 1
            if _drain_depth == 0:
                _active_owner_name = None
            else:
                _active_owner_name = previous_owner


def get_active_drain_owner() -> str | None:
    """Return the active drain owner name, or None if idle."""
    with _drain_lock:
        return _active_owner_name


def get_drain_depth() -> int:
    """Return current drain recursion depth."""
    with _drain_lock:
        return _drain_depth


def is_vcl_pump_allowed() -> bool:
    """Return True if native VCL pumping is safe (depth <= 1)."""
    with _drain_lock:
        return _drain_depth <= 1


def note_suppressed_vcl_pump() -> None:
    """Increment suppressed VCL pump diagnostic counter."""
    global _suppressed_vcl_count
    with _drain_lock:
        _suppressed_vcl_count += 1


def get_suppressed_vcl_count() -> int:
    """Diagnostic helper: return total suppressed secondary VCL pumps."""
    with _drain_lock:
        return _suppressed_vcl_count


def reset_sentry_state() -> None:
    """Test hook: reset sentry state completely."""
    global _active_owner_name, _drain_depth, _suppressed_vcl_count
    with _drain_lock:
        _active_owner_name = None
        _drain_depth = 0
        _suppressed_vcl_count = 0
