# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile-time type-state token for UNO main-thread affinity.

Stock type checkers (Mypy, Basedpyright, Ty) cannot track thread affinity
by default. This module defines a nominal `MainThreadToken` type that can
only be constructed/minted via `require_main_thread()` or supplied by
`execute_on_main_thread()`. Red functions requiring main thread access can
declare `token: MainThreadToken` or `token: MainThreadToken | None = None`
in their signatures, enabling build-time type verification.

Unused in plugin/ today: runtime affinity is Opengrep taint plus thread_guard
(docs/framework-uno-thread-safety.md §11).
"""

from __future__ import annotations

from typing import NewType

# Nominal token type representing proof that execution is on the LibreOffice main thread.
MainThreadToken = NewType("MainThreadToken", object)

_TOKEN_INSTANCE = MainThreadToken(object())


def require_main_thread() -> MainThreadToken:
    """Assert execution is on the LibreOffice main thread and return a valid MainThreadToken.

    When the guard is stubbed off (release OXT), this still returns the token
    even off the UI thread — it is not proof of main-thread in shipped builds.
    """
    from plugin.framework.thread_guard import assert_main_thread, on_main_thread

    if not on_main_thread():
        assert_main_thread("require_main_thread")
    return _TOKEN_INSTANCE
