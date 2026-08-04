from __future__ import annotations

import pytest
from plugin.framework.async_drain_guard import (
    drain_owner_sentry,
    get_active_drain_owner,
    get_drain_depth,
    is_vcl_pump_allowed,
    note_suppressed_vcl_pump,
    get_suppressed_vcl_count,
    reset_sentry_state,
    NestedDrainOwnerError,
)


@pytest.fixture(autouse=True)
def _clean_sentry_state():
    reset_sentry_state()
    yield
    reset_sentry_state()


def test_async_drain_guard_single_owner():
    assert get_active_drain_owner() is None
    assert get_drain_depth() == 0
    assert is_vcl_pump_allowed() is True

    with drain_owner_sentry("chat_stream"):
        assert get_active_drain_owner() == "chat_stream"
        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True

    assert get_active_drain_owner() is None
    assert get_drain_depth() == 0


def test_async_drain_guard_prevents_nested_different_owners():
    with drain_owner_sentry("chat_stream"):
        with pytest.raises(NestedDrainOwnerError, match="Nested UI drain attempted by 'mcp_stream'"):
            with drain_owner_sentry("mcp_stream"):
                pass


def test_async_drain_guard_reentrant_same_owner_updates_depth():
    with drain_owner_sentry("chat_stream"):
        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True
        with drain_owner_sentry("chat_stream"):
            assert get_drain_depth() == 2
            assert is_vcl_pump_allowed() is False

        assert get_drain_depth() == 1
        assert is_vcl_pump_allowed() is True


def test_async_drain_guard_suppressed_vcl_counter():
    assert get_suppressed_vcl_count() == 0
    note_suppressed_vcl_pump()
    note_suppressed_vcl_pump()
    assert get_suppressed_vcl_count() == 2
