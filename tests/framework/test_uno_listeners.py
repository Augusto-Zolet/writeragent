# tests/framework/test_uno_listeners.py
# Tests for unified UNO event listeners and stubs.

import logging
from unittest.mock import MagicMock
import pytest

from tests.testing_utils import setup_uno_mocks
setup_uno_mocks()

from plugin.framework.uno_listeners import (
    _catch_and_log,
    BaseListener,
    BaseActionListener,
    BaseItemListener,
    BaseTextListener,
    BaseKeyListener,
    BaseWindowListener,
    BaseDocumentEventListener,
    BaseCloseListener,
    BaseTerminateListener,
)

def test_catch_and_log_decorator(caplog):
    """Verify that @_catch_and_log swallows and logs unhandled exceptions."""
    class DummyListener:
        @_catch_and_log
        def someMethod(self, ev):
            raise RuntimeError("Test error inside listener")

    listener = DummyListener()
    
    # Executing the decorated method should not raise an exception
    with caplog.at_level(logging.ERROR):
        listener.someMethod(MagicMock())
        
    assert len(caplog.records) == 1
    assert "Test error inside listener" in caplog.text
    assert "DummyListener unhandled exception in someMethod" in caplog.text


def test_base_listener_disposing():
    """Verify that disposing is callable and safe."""
    listener = BaseListener()
    # Should run with no errors
    listener.disposing(MagicMock())


def test_base_action_listener():
    """Verify action listener invokes the correct subclass callback."""
    class MyActionListener(BaseActionListener):
        def __init__(self):
            super().__init__()
            self.called = False
            self.event = None

        def on_action_performed(self, rEvent):
            self.called = True
            self.event = rEvent

    listener = MyActionListener()
    ev = MagicMock()
    listener.actionPerformed(ev)
    assert listener.called is True
    assert listener.event == ev


def test_base_item_listener():
    """Verify item listener invokes the correct subclass callback."""
    class MyItemListener(BaseItemListener):
        def __init__(self):
            super().__init__()
            self.called = False

        def on_item_state_changed(self, rEvent):
            self.called = True

    listener = MyItemListener()
    listener.itemStateChanged(MagicMock())
    assert listener.called is True


def test_base_text_listener():
    """Verify text listener invokes the correct subclass callback."""
    class MyTextListener(BaseTextListener):
        def __init__(self):
            super().__init__()
            self.called = False

        def on_text_changed(self, rEvent):
            self.called = True

    listener = MyTextListener()
    listener.textChanged(MagicMock())
    assert listener.called is True


def test_base_key_listener():
    """Verify key listener invokes the correct subclass callback."""
    class MyKeyListener(BaseKeyListener):
        def __init__(self):
            super().__init__()
            self.pressed = False
            self.released = False

        def on_key_pressed(self, e):
            self.pressed = True

        def on_key_released(self, e):
            self.released = True

    listener = MyKeyListener()
    listener.keyPressed(MagicMock())
    listener.keyReleased(MagicMock())
    assert listener.pressed is True
    assert listener.released is True


def test_base_window_listener():
    """Verify window listener invokes all resize/move/show/hide callbacks."""
    class MyWindowListener(BaseWindowListener):
        def __init__(self):
            super().__init__()
            self.resized = False
            self.moved = False
            self.shown = False
            self.hidden = False

        def on_window_resized(self, rEvent):
            self.resized = True

        def on_window_moved(self, rEvent):
            self.moved = True

        def on_window_shown(self, rEvent):
            self.shown = True

        def on_window_hidden(self, rEvent):
            self.hidden = True

    listener = MyWindowListener()
    ev = MagicMock()
    listener.windowResized(ev)
    listener.windowMoved(ev)
    listener.windowShown(ev)
    listener.windowHidden(ev)

    assert listener.resized is True
    assert listener.moved is True
    assert listener.shown is True
    assert listener.hidden is True


def test_base_document_event_listener():
    """Verify document event listener invokes the correct subclass callback."""
    class MyDocListener(BaseDocumentEventListener):
        def __init__(self):
            super().__init__()
            self.called = False
            self.event = None

        def on_document_event(self, Event):
            self.called = True
            self.event = Event

    listener = MyDocListener()
    ev = MagicMock()
    listener.documentEventOccured(ev)
    assert listener.called is True
    assert listener.event == ev


def test_base_close_listener():
    """Verify close listener invokes the correct subclass callbacks."""
    class MyCloseListener(BaseCloseListener):
        def __init__(self):
            super().__init__()
            self.query_called = False
            self.notify_called = False

        def on_query_closing(self, Source, GetsOwnership):
            self.query_called = True

        def on_notify_closing(self, Source):
            self.notify_called = True

    listener = MyCloseListener()
    listener.queryClosing(MagicMock(), True)
    listener.notifyClosing(MagicMock())
    assert listener.query_called is True
    assert listener.notify_called is True


def test_base_terminate_listener():
    """Verify terminate listener invokes the correct subclass callbacks."""
    class MyTerminateListener(BaseTerminateListener):
        def __init__(self):
            super().__init__()
            self.query_called = False
            self.notify_called = False

        def on_query_termination(self, Event):
            self.query_called = True

        def on_notify_termination(self, Event):
            self.notify_called = True

    listener = MyTerminateListener()
    listener.queryTermination(MagicMock())
    listener.notifyTermination(MagicMock())
    assert listener.query_called is True
    assert listener.notify_called is True
