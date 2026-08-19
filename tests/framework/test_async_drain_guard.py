from __future__ import annotations

import pytest
from plugin.framework.async_drain_guard import (
    NestedDrainOwnerError,
    drain_owner_scope,
    get_active_drain_owner,
    get_drain_depth,
    get_drain_owner,
    get_suppressed_vcl_count,
    get_suppressed_vcl_pump_count,
    is_vcl_pump_allowed,
    note_suppressed_vcl_pump,
    reset_sentry_state,
    reset_suppressed_vcl_pump_count,
)
import plugin.framework.queue_executor as qe


@pytest.fixture(autouse=True)
def _clean_sentry_state():
    reset_sentry_state()
    yield
    reset_sentry_state()


def test_async_drain_guard_single_owner():
    assert get_drain_owner() is None
    assert get_active_drain_owner() is None
    assert get_drain_depth() == 0
    assert is_vcl_pump_allowed() is True

    with drain_owner_scope("chat_stream"):
        assert get_drain_owner() == "chat_stream"
        assert get_active_drain_owner() == "chat_stream"
        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True

    assert get_drain_owner() is None
    assert get_active_drain_owner() is None
    assert get_drain_depth() == 0


def test_async_drain_guard_prevents_nested_different_owners():
    with drain_owner_scope("chat_stream"):
        with pytest.raises(NestedDrainOwnerError, match="Nested UI drain attempted by 'mcp_stream'"):
            with drain_owner_scope("mcp_stream"):
                pass


def test_async_drain_guard_reentrant_same_owner_updates_depth():
    with drain_owner_scope("chat_stream"):
        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True
        with drain_owner_scope("chat_stream"):
            assert get_drain_depth() == 2
            assert is_vcl_pump_allowed() is False

        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True


def test_async_drain_guard_suppressed_vcl_counter():
    assert get_suppressed_vcl_pump_count() == 0
    assert get_suppressed_vcl_count() == 0
    note_suppressed_vcl_pump("chat_stream")
    note_suppressed_vcl_pump()
    assert get_suppressed_vcl_pump_count() == 2
    assert get_suppressed_vcl_count() == 2

    reset_suppressed_vcl_pump_count()
    assert get_suppressed_vcl_pump_count() == 0


def test_queue_executor_reexports_async_drain_guard():
    assert qe.NestedDrainOwnerError is NestedDrainOwnerError
    assert qe.drain_owner_scope is drain_owner_scope
    assert qe.get_drain_owner is get_drain_owner
    assert qe.get_suppressed_vcl_pump_count is get_suppressed_vcl_pump_count
    assert qe.reset_suppressed_vcl_pump_count is reset_suppressed_vcl_pump_count
    assert qe._note_suppressed_vcl_pump is note_suppressed_vcl_pump
