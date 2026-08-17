# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for review_scan token + fail-closed enumeration (no UNO)."""

from plugin.writer.review_scan import (
    TOKEN_PREFIX,
    is_agent_token,
    make_agent_token,
    redline_is_agent_change,
    scan_redlines,
    session_token_prefix,
    snapshot_redline_ids,
)


def test_make_agent_token_and_prefix():
    assert make_agent_token("abc", 2) == "wa-review:abc:2"
    assert session_token_prefix("abc") == "wa-review:abc:"
    assert session_token_prefix("abc").startswith(TOKEN_PREFIX)


def test_is_agent_token():
    assert is_agent_token("wa-review:s:0") is True
    assert is_agent_token("user note") is False
    assert is_agent_token("") is False
    assert is_agent_token(None) is False


def test_redline_is_agent_change_unreadable():
    class _Bad:
        def getPropertyValue(self, name):
            raise RuntimeError("gone")

    assert redline_is_agent_change(_Bad()) == (False, False)


def test_scan_redlines_unreliable_when_count_exceeds_enum():
    class _Enum:
        def __init__(self, items):
            self._items = list(items)

        def hasMoreElements(self):
            return bool(self._items)

        def nextElement(self):
            return self._items.pop(0)

    class _Reds:
        def getCount(self):
            return 2

        def createEnumeration(self):
            return _Enum(["only-one"])

    class _Doc:
        def getRedlines(self):
            return _Reds()

    reliable, seen, total = scan_redlines(_Doc(), lambda rl: True)
    assert reliable is False
    assert seen == 1
    assert total == 2


def test_snapshot_redline_ids_complete():
    class _Rl:
        def __init__(self, ident):
            self._ident = ident

        def getPropertyValue(self, name):
            return self._ident

    class _Enum:
        def __init__(self, items):
            self._items = list(items)

        def hasMoreElements(self):
            return bool(self._items)

        def nextElement(self):
            return self._items.pop(0)

    class _Reds:
        def __init__(self, items):
            self._items = items

        def getCount(self):
            return len(self._items)

        def createEnumeration(self):
            return _Enum(self._items)

    class _Doc:
        def getRedlines(self):
            return _Reds([_Rl("a"), _Rl("b")])

    ids, ok = snapshot_redline_ids(_Doc())
    assert ok is True
    assert ids == {"a", "b"}
