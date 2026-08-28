# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Unit tests for sidebar query Enter-to-send key classification and send dispose."""

import sys
import unittest
from unittest.mock import MagicMock, patch

from plugin.framework.config_schema import _get_schema_default
from plugin.chatbot.panel import QueryKeyListener, SendButtonListener, query_enter_triggers_primary_send
from plugin.framework.queue_executor import SendCancellation


class QueryEnterSendTests(unittest.TestCase):
    def test_enter_without_shift_triggers(self):
        self.assertTrue(query_enter_triggers_primary_send(1280, 0))

    def test_shift_enter_does_not_trigger(self):
        self.assertFalse(query_enter_triggers_primary_send(1280, 1))

    def test_shift_with_other_modifiers(self):
        self.assertFalse(query_enter_triggers_primary_send(1280, 1 | 2))

    def test_non_return_key_ignored(self):
        self.assertFalse(query_enter_triggers_primary_send(1279, 0))

    def test_doc_yaml_default_enter_sends_true(self):
        self.assertIs(_get_schema_default("doc.chat_enter_key_sends_message"), True)


def _make_send_listener() -> SendButtonListener:
    session = MagicMock()
    session.messages = [{"role": "system", "content": "test"}]
    return SendButtonListener(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        session,
    )


class SendDisposeTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(sys.modules, {"plugin.main": MagicMock()}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disposing_cancels_in_flight_send(self) -> None:
        listener = _make_send_listener()
        scope = SendCancellation()
        listener._send_cancellation = scope
        checker = listener.resolve_stop_checker()
        self.assertFalse(checker())
        listener.disposing(None)
        self.assertTrue(scope.is_cancelled())
        self.assertTrue(checker())
        self.assertTrue(listener._stop_requested_fallback)
        self.assertIsNone(listener.ctx)
        self.assertIsNone(listener.panel)

    def test_disposing_without_active_send_still_latches_stop(self) -> None:
        listener = _make_send_listener()
        listener._send_cancellation = None
        listener.disposing(None)
        self.assertTrue(listener._stop_requested_fallback)
        self.assertIsNone(listener.ctx)
        self.assertIsNone(listener.panel)


class _MockDisposedException(Exception):
    """Name must include DisposedException so is_disposed_exception matches."""


class _ConsumeEvent:
    def __init__(self) -> None:
        object.__setattr__(self, "KeyCode", 1280)
        object.__setattr__(self, "Modifiers", 0)
        object.__setattr__(self, "Consume", False)

    def __setattr__(self, name, value):
        if name == "Consume":
            raise _MockDisposedException("event disposed")
        object.__setattr__(self, name, value)


class QueryKeyListenerDisposeTests(unittest.TestCase):
    def test_consume_disposed_still_sends(self) -> None:
        send_listener = MagicMock()
        send_model = MagicMock()
        send_model.Enabled = True
        send_listener.send_control.getModel.return_value = send_model
        listener = QueryKeyListener(send_listener)
        event = _ConsumeEvent()
        with patch("plugin.framework.config.get_config_bool", return_value=True):
            listener.on_key_pressed(event)
        send_listener.on_action_performed.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
