# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Packet F: HTTP / SSE errors then hello on a live chat sidebar.

Run via ``make test-mock-sidebar`` (visible soffice, LibreOffice user profile).
"""

from __future__ import annotations

import os
import time
import unittest
from typing import Any

from plugin.testing_runner import native_test, setup, teardown

from tests.chatbot.mock_llm_harness import (
    start_mock_sidebar_session,
    stop_mock_sidebar_session,
)

_session = None


def _ensure_writer_doc(ctx) -> None:
    from plugin.chatbot.sidebar_test_hooks import current_component, desktop_from_ctx
    from plugin.doc.doc_type import is_writer

    doc = current_component(ctx)
    if doc is not None and is_writer(doc):
        return
    desktop_from_ctx(ctx).loadComponentFromURL("private:factory/swriter", "_default", 0, ())
    time.sleep(1.0)


@setup
def _setup_mock(ctx):
    global _session
    from plugin.framework.config import init_config

    if os.environ.get("WRITERAGENT_UNO_USER_PROFILE") != "1":
        raise unittest.SkipTest("use make test-mock-sidebar (LibreOffice user profile)")

    init_config(ctx)
    # Import hooks before later panel creates; factory WeakSet also sees panels
    # that were wired before this module loaded (debug-only).
    import plugin.chatbot.sidebar_test_hooks  # noqa: F401

    from plugin.chatbot.sidebar_test_hooks import (
        adopt_runtime_send_listeners,
        ensure_sidebar_chat_mode,
        send_listener,
        wait_for_chat_dialog_controls,
    )

    _ensure_writer_doc(ctx)
    # Point writeragent.json at the mock *before* showing the deck so the live
    # OXT send path is not still using the user's real endpoint.
    _session = start_mock_sidebar_session(delay_ms=20, offline=True)
    controls = wait_for_chat_dialog_controls(ctx, timeout=20.0)
    adopt_runtime_send_listeners()
    sl = send_listener()
    if sl is None and controls is None:
        from plugin.chatbot.sidebar_test_hooks import current_component, sidebar_deck_names

        names = []
        try:
            names = sidebar_deck_names(ctx, current_component(ctx))
        except Exception:
            names = []
        raise AssertionError(
            "WriterAgent chat sidebar not wired after showing WriterAgentDeck "
            "(View → Sidebar must be on). decks=%s" % (names,)
        )
    ensure_sidebar_chat_mode(controls)
    _session.controls = controls
    _session.listener = sl


@teardown
def _teardown_mock():
    global _session
    from plugin.chatbot.sidebar_test_hooks import press_stop, send_listener, send_state

    sl = send_listener()
    if sl is not None:
        try:
            if send_state(listener=sl).is_busy:
                press_stop(listener=sl)
        except Exception:
            pass
    if _session is not None:
        # Clear fail/delay mutations so a partial run does not leave the mock wedged.
        try:
            _session.config.fail = "none"
            _session.config.delay_ms = 20
        except Exception:
            pass
    stop_mock_sidebar_session(_session)
    _session = None


def _control_text(ctrl) -> str:
    try:
        if hasattr(ctrl, "getText"):
            return str(ctrl.getText() or "")
        model = ctrl.getModel()
        return str(getattr(model, "Text", "") or "")
    except Exception:
        return ""


def _transcript() -> str:
    sl = getattr(_session, "listener", None)
    if sl is not None:
        from plugin.chatbot.sidebar_test_hooks import transcript_text

        return transcript_text(listener=sl)
    controls = getattr(_session, "controls", None) or {}
    for name in ("response_rich", "response"):
        if name in controls:
            return _control_text(controls[name])
    return ""


def _send_and_wait(text: str, timeout: float = 60.0, *, wait_for: str | None = None):
    from plugin.chatbot.sidebar_test_hooks import (
        press_send,
        set_query_text,
        set_query_text_via_controls,
        uno_click,
        wait_controls_send_finished,
        wait_idle,
    )

    before = _transcript()
    sl = getattr(_session, "listener", None)
    if sl is not None:
        set_query_text(text, listener=sl)
        press_send(listener=sl)
        assert wait_idle(listener=sl, timeout=timeout), "send did not go idle: %r" % text
        if wait_for:
            body = _transcript()
            suffix = body[len(before) :] if body.startswith(before) else body
            assert wait_for.lower() in suffix.lower() or wait_for.lower() in body.lower(), (
                "after send %r expected %r in %r" % (text, wait_for, body[-500:])
            )
        return sl
    controls = getattr(_session, "controls", None)
    assert controls is not None, "no SendButtonListener and no chat dialog controls"
    set_query_text_via_controls(controls, text)
    time.sleep(0.2)
    uno_click(controls["send"])
    assert wait_controls_send_finished(
        controls,
        timeout=timeout,
        transcript_fn=_transcript,
        wait_for=wait_for,
        before=before,
    ), "send did not finish: %r transcript=%r" % (text, _transcript()[-500:])
    return None


def _press_stop() -> None:
    """Cancel in-flight send (URP ActionEvent path when listener is out-of-process)."""
    sl = getattr(_session, "listener", None)
    if sl is not None:
        from plugin.chatbot.sidebar_test_hooks import press_stop

        press_stop(listener=sl)
        return
    controls = getattr(_session, "controls", None)
    assert controls is not None and "stop" in controls, "no Stop control"
    from plugin.chatbot.sidebar_test_hooks import uno_click

    uno_click(controls["stop"])


def _wait_stop_enabled(timeout: float = 10.0) -> bool:
    """True when Stop is Enabled (send in flight) over URP."""
    from plugin.chatbot.sidebar_test_hooks import control_enabled

    controls = getattr(_session, "controls", None) or {}
    stop = controls.get("stop")
    if stop is None:
        sl = getattr(_session, "listener", None)
        if sl is not None:
            from plugin.chatbot.sidebar_test_hooks import send_state

            deadline = time.monotonic() + timeout
            while time.monotonic() <= deadline:
                if send_state(listener=sl).is_busy:
                    return True
                time.sleep(0.1)
            return False
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        if control_enabled(stop) is True:
            return True
        time.sleep(0.1)
    return False


def _hello_ok() -> None:
    """Send hello and require a new Assistant turn (rich control shows plain text, not raw HTML)."""
    sl = getattr(_session, "listener", None)
    before = _transcript()
    if sl is not None:
        from plugin.chatbot.sidebar_test_hooks import next_hello_ok

        assert next_hello_ok(listener=sl, timeout=60.0), "recovery hello failed"
        return
    _send_and_wait("hello", timeout=60.0)
    body = _transcript()
    suffix = body[len(before) :] if body.startswith(before) else body
    blob = suffix if suffix else body
    low = blob.lower()
    # Rotating HTML templates paste as plain text (lists/tables), not raw tags.
    assert "assistant:" in low and (
        "hello" in low or "mock" in low or "streamed as plain" in low or "table" in low or "numbered steps" in low
    ), ("hello reply missing: %r" % body[-400:])


def _reset_mock_runtime() -> None:
    """Clear fail/delay so a prior F5/F6/F16 cannot poison later cases."""
    if _session is None:
        return
    _session.config.fail = "none"
    _session.config.delay_ms = 20
    _session.config.fail_after_chunks = 4
    _session.config.sse_comments = False
    try:
        if _wait_stop_enabled(timeout=0.3):
            _press_stop()
            time.sleep(0.5)
    except Exception:
        pass


def _assert_errorish(body: str, *needles: str) -> None:
    lower = body.lower()
    if "[api error:" in lower:
        return
    for needle in needles:
        if needle.lower() in lower:
            return
    raise AssertionError("expected error markers %r in %r" % (needles, body[-500:]))


def _rebind_mock(**flags: Any) -> None:
    """Restart the in-process mock on a new port and point config at it.

    ``LlmClient`` keeps a persistent ``HTTPConnection`` whose socket timeout is
    fixed at connect time. Changing ``request_timeout`` alone does not update
    an existing socket — rebinding the endpoint forces a fresh connection.
    """
    import threading
    from http.server import ThreadingHTTPServer

    from plugin.framework.config import set_api_key_for_endpoint, set_config
    from scripts.mock_llm_server import make_handler_class

    assert _session is not None
    for key, value in flags.items():
        setattr(_session.config, key, value)
    try:
        _session.httpd.shutdown()
        _session.thread.join(timeout=2)
    except Exception:
        pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler_class(_session.config))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    base_url = "http://%s:%s" % (host, port)
    _session.httpd = httpd
    _session.thread = thread
    _session.base_url = base_url
    set_config("endpoint", base_url)
    set_api_key_for_endpoint(base_url, "mock-key")
    if os.environ.get("WRITERAGENT_UNO_USER_PROFILE") == "1":
        time.sleep(2.1)


@native_test
def test_f1_crash_the_stream_then_hello(ctx):
    _send_and_wait("crash the stream", wait_for="API error")
    body = _transcript()
    assert "[API error:" in body or "HTTP Error 500" in body or "500" in body, (
        "F1 expected 500 in transcript, got %r" % body[-500:]
    )
    _hello_ok()


@native_test
def test_f2_rate_limit_then_hello(ctx):
    # Spec: rate-limit only (500-then-429 is F15).
    _send_and_wait("rate limit", wait_for="429")
    body = _transcript()
    assert "429" in body or "Rate limited" in body, "F2 expected 429 in transcript, got %r" % body[-500:]
    _hello_ok()


@native_test
def test_f3a_hang_the_stream_then_hello(ctx):
    _reset_mock_runtime()
    # Hang drops after a few SSE chunks (EOF). Do not wait request_timeout (120s).
    _send_and_wait("hang the stream", timeout=20.0)
    body = _transcript()
    # EOF mid-stream may leave partial ramble text and/or an API/connection error.
    low = body.lower()
    assert (
        "[api error:" in low
        or "stopped" in low
        or "connection" in low
        or "timed out" in low
        or "word0" in low
    ), "F3a expected hang symptom in transcript, got %r" % body[-500:]
    _hello_ok()


@native_test
def test_f3b_hang_stop_mouse_skipped(ctx):
    raise unittest.SkipTest(
        "F3b press_stop_mouse needs in-process SendButtonListener; "
        "URP only has ActionEvent via uno_click (covered by F17)"
    )


@native_test
def test_f4_sse_pings_then_hello(ctx):
    _send_and_wait("sse pings", wait_for="mock")
    body = _transcript()
    assert "mock" in body.lower() or "assistant:" in body.lower(), "F4 expected HTML chat, got %r" % body[-400:]
    _hello_ok()


@native_test
def test_f5_fail_all_http500_then_hello(ctx):
    assert _session is not None
    _session.config.fail = "http500"
    try:
        _send_and_wait("hello", wait_for="API error", timeout=30.0)
        body = _transcript()
        _assert_errorish(body, "500", "API error")
    finally:
        _session.config.fail = "none"
    _hello_ok()


@native_test
def test_f6_ramble_hang_then_hello(ctx):
    assert _session is not None
    _reset_mock_runtime()
    _session.config.fail = "hang"
    _session.config.fail_after_chunks = 4
    try:
        from plugin.chatbot.sidebar_test_hooks import (
            set_query_text_via_controls,
            uno_click,
            wait_controls_send_finished,
        )

        controls = getattr(_session, "controls", None)
        before = _transcript()
        if controls is not None:
            set_query_text_via_controls(controls, "keep talking")
            time.sleep(0.2)
            uno_click(controls["send"])
            if _wait_stop_enabled(timeout=8.0):
                _press_stop()
            assert wait_controls_send_finished(
                controls,
                timeout=25.0,
                transcript_fn=_transcript,
                before=before,
            ), "F6 did not go idle: %r" % _transcript()[-400:]
        else:
            _send_and_wait("keep talking", timeout=25.0)
    finally:
        _session.config.fail = "none"
        _session.config.fail_after_chunks = 4
    _hello_ok()


@native_test
def test_f7_error_401_then_hello(ctx):
    _send_and_wait("error 401", wait_for="API error")
    body = _transcript()
    _assert_errorish(body, "401")
    _hello_ok()


@native_test
def test_f8_error_403_then_hello(ctx):
    _send_and_wait("error 403", wait_for="API error")
    body = _transcript()
    _assert_errorish(body, "403")
    _hello_ok()


@native_test
def test_f9_malformed_sse_then_hello(ctx):
    _send_and_wait("malformed sse", timeout=30.0)
    body = _transcript()
    assert "assistant:" in body.lower() or "[api error:" in body.lower(), (
        "F9 expected recovery stream or error, got %r" % body[-400:]
    )
    _hello_ok()


@native_test
def test_f10_truncated_json_then_hello(ctx):
    _send_and_wait("truncated json", timeout=30.0)
    body = _transcript()
    assert "assistant:" in body.lower() or "[api error:" in body.lower(), (
        "F10 expected recovery stream or error, got %r" % body[-400:]
    )
    _hello_ok()


@native_test
def test_f11_two_dones_then_hello(ctx):
    _send_and_wait("two dones", wait_for="mock")
    body = _transcript()
    assert "assistant:" in body.lower() or "mock" in body.lower(), "F11 expected single HTML reply, got %r" % body[-400:]
    _hello_ok()


@native_test
def test_f12_empty_body_then_hello(ctx):
    _send_and_wait("empty body", timeout=30.0)
    body = _transcript()
    _assert_errorish(body, "API error", "No text from model", "Debug", "empty")
    _hello_ok()


@native_test
def test_f13_connection_reset_then_hello(ctx):
    _send_and_wait("connection reset", timeout=30.0)
    body = _transcript()
    _assert_errorish(body, "API error", "Connection", "reset", "Remote")
    _hello_ok()


@native_test
def test_f14_429_then_immediate_hello(ctx):
    _send_and_wait("error 429", wait_for="429")
    _hello_ok()


@native_test
def test_f15_500_then_429_then_hello(ctx):
    _send_and_wait("crash the stream", wait_for="API error")
    before_429 = _transcript()
    _send_and_wait("rate limit", wait_for="429")
    body = _transcript()
    assert "429" in body or "Rate limited" in body, "F15 expected 429, got %r" % body[-500:]
    # Prior 500 line must survive (no HTML-rerender wipe).
    if "[API error:" in before_429 or "HTTP Error 500" in before_429 or "500" in before_429:
        assert "[API error:" in body or "HTTP Error 500" in body or "500" in body
    _hello_ok()


@native_test
def test_f16_timeout_then_hello(ctx):
    """Client request_timeout shorter than mock inter-chunk delay → ERROR then hello."""
    from plugin.framework.config import get_config_int, set_config

    assert _session is not None
    _reset_mock_runtime()
    saved_timeout = get_config_int("request_timeout")
    try:
        set_config("request_timeout", 3)
        # New port + hang with slow chunks: fresh socket uses timeout=3.
        _rebind_mock(fail="hang", fail_after_chunks=50, delay_ms=8000)
        _send_and_wait("hello", timeout=25.0)
        body = _transcript()
        _assert_errorish(body, "API error", "Timed Out", "timeout", "Connection", "timed out")
    finally:
        try:
            _press_stop()
        except Exception:
            pass
        set_config("request_timeout", saved_timeout)
        _rebind_mock(fail="none", fail_after_chunks=4, delay_ms=20)
    _hello_ok()


@native_test
def test_f17_stop_during_hang_then_hello(ctx):
    from plugin.chatbot.sidebar_test_hooks import (
        set_query_text_via_controls,
        uno_click,
        wait_controls_send_finished,
    )

    _reset_mock_runtime()
    controls = getattr(_session, "controls", None)
    before = _transcript()
    if controls is not None:
        set_query_text_via_controls(controls, "hang the stream")
        time.sleep(0.2)
        uno_click(controls["send"])
        assert _wait_stop_enabled(timeout=10.0), "F17 Stop never enabled during hang"
        _press_stop()
        assert wait_controls_send_finished(
            controls,
            timeout=20.0,
            transcript_fn=_transcript,
            before=before,
        ), "F17 did not go idle after Stop: %r" % _transcript()[-400:]
    else:
        sl = getattr(_session, "listener", None)
        assert sl is not None
        from plugin.chatbot.sidebar_test_hooks import press_send, set_query_text, wait_idle

        set_query_text("hang the stream", listener=sl)
        press_send(listener=sl)
        assert _wait_stop_enabled(timeout=10.0)
        _press_stop()
        assert wait_idle(listener=sl, timeout=20.0)
    _hello_ok()


@native_test
def test_f18_event_ping_then_hello(ctx):
    _reset_mock_runtime()
    _send_and_wait("event ping", wait_for="mock")
    body = _transcript()
    assert "mock" in body.lower() or "assistant:" in body.lower(), "F18 expected HTML chat, got %r" % body[-400:]
    _hello_ok()
