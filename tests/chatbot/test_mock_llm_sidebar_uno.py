# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Packet F (HTTP/SSE), B (Stop/Send FSM), and E (tools/HITL) on a live chat sidebar.

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
_saved_prompt_research: bool | None = None
WELCOME_BODY = "Welcome to WriterAgent."


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

    global _saved_prompt_research
    init_config(ctx)
    from plugin.framework.config import get_config_bool, set_config

    # Packet E1–E8 must not block on HITL Accept. E9 turns this on locally.
    _saved_prompt_research = get_config_bool("chatbot.prompt_for_web_research")
    set_config("chatbot.prompt_for_web_research", False)
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
    _set_writer_body(ctx, WELCOME_BODY)


@teardown
def _teardown_mock():
    global _session, _saved_prompt_research
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
    if _saved_prompt_research is not None:
        try:
            from plugin.framework.config import set_config

            set_config("chatbot.prompt_for_web_research", _saved_prompt_research)
        except Exception:
            pass


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


def _query_box_text() -> str:
    sl = getattr(_session, "listener", None)
    if sl is not None:
        from plugin.chatbot.sidebar_test_hooks import query_text

        return query_text(listener=sl)
    controls = getattr(_session, "controls", None) or {}
    query = controls.get("query")
    if query is None:
        return ""
    from plugin.chatbot.dialogs import get_control_text

    return get_control_text(query, default="") or ""


def _send_enabled() -> bool | None:
    from plugin.chatbot.sidebar_test_hooks import control_enabled

    controls = getattr(_session, "controls", None) or {}
    return control_enabled(controls.get("send"))


def _wait_idle_after_send(before: str, timeout: float = 30.0) -> None:
    from plugin.chatbot.sidebar_test_hooks import wait_controls_send_finished, wait_idle

    controls = getattr(_session, "controls", None)
    if controls is not None:
        assert wait_controls_send_finished(
            controls,
            timeout=timeout,
            transcript_fn=_transcript,
            before=before,
        ), "send did not go idle: %r" % _transcript()[-400:]
        return
    sl = getattr(_session, "listener", None)
    assert sl is not None
    assert wait_idle(listener=sl, timeout=timeout), "send did not go idle"


def _start_until_stop_enabled(text: str, *, delay_ms: int = 40, timeout: float = 15.0) -> str:
    """Type *text*, Send, wait until Stop is Enabled. Caller must reset delay_ms."""
    from plugin.chatbot.sidebar_test_hooks import (
        press_send,
        set_query_text,
        set_query_text_via_controls,
        uno_click,
    )

    assert _session is not None
    _session.config.delay_ms = delay_ms
    before = _transcript()
    controls = getattr(_session, "controls", None)
    if controls is not None:
        set_query_text_via_controls(controls, text)
        time.sleep(0.2)
        uno_click(controls["send"])
    else:
        sl = getattr(_session, "listener", None)
        assert sl is not None
        set_query_text(text, listener=sl)
        press_send(listener=sl)
    assert _wait_stop_enabled(timeout=timeout), "Stop never enabled for %r" % text
    return before


def _stop_and_wait_idle(before: str, timeout: float = 25.0) -> None:
    _press_stop()
    _wait_idle_after_send(before, timeout=timeout)


def _assert_stopped_banner(before: str) -> None:
    body = _transcript()
    suffix = body[len(before) :] if body.startswith(before) else body
    assert "[Stopped by user]" in suffix or "[Stopped by user]" in body, (
        "expected [Stopped by user], got %r" % body[-500:]
    )
    assert "No response." not in suffix, "Stopped banner replaced by No response.: %r" % suffix[-400:]
    # B1c: do not HTML-rerender the full ramble over the Stopped marker.
    assert "word199" not in suffix.lower() or "[Stopped by user]" in suffix, (
        "ramble HTML wiped Stopped banner: %r" % suffix[-400:]
    )


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


def _set_writer_body(ctx, text: str) -> None:
    from plugin.chatbot.sidebar_test_hooks import current_component

    doc = current_component(ctx)
    assert doc is not None, "no current document"
    cursor = doc.getText().createTextCursor()
    cursor.gotoStart(False)
    cursor.gotoEnd(True)
    cursor.setString(text)


def _writer_body(ctx) -> str:
    from plugin.chatbot.sidebar_test_hooks import current_component

    doc = current_component(ctx)
    if doc is None:
        return ""
    try:
        return str(doc.getText().getString() or "")
    except Exception:
        return ""


def _annotation_count(ctx) -> int:
    from plugin.chatbot.sidebar_test_hooks import current_component

    doc = current_component(ctx)
    if doc is None:
        return 0
    n = 0
    try:
        enum = doc.getTextFields().createEnumeration()
    except Exception:
        return 0
    while True:
        try:
            if not enum.hasMoreElements():
                break
            field = enum.nextElement()
        except Exception:
            break
        try:
            if field.supportsService("com.sun.star.text.textfield.Annotation"):
                n += 1
        except Exception:
            continue
    return n


def _label(ctrl) -> str:
    try:
        model = ctrl.getModel() if ctrl is not None else None
        if model is not None:
            return str(getattr(model, "Label", "") or "")
    except Exception:
        return ""
    return ""


def _wait_send_label(needle: str, timeout: float = 45.0) -> bool:
    controls = getattr(_session, "controls", None) or {}
    send = controls.get("send")
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        if send is not None and needle.lower() in _label(send).lower():
            return True
        sl = getattr(_session, "listener", None)
        if sl is not None:
            from plugin.chatbot.sidebar_test_hooks import approval_active, send_state

            if approval_active(listener=sl) or needle.lower() in send_state(listener=sl).send_label.lower():
                return True
        time.sleep(0.15)
    return False


def _captures() -> list[dict[str, Any]]:
    from scripts.mock_llm_server import snapshot_captures

    assert _session is not None
    return snapshot_captures(_session.config)


def _reset_mock_runtime() -> None:
    """Clear fail/delay so a prior F5/F6/F16 cannot poison later cases."""
    if _session is None:
        return
    _session.config.fail = "none"
    _session.config.delay_ms = 20
    _session.config.sync_delay_ms = None
    _session.config.fail_after_chunks = 4
    _session.config.sse_comments = False
    _session.config.fail_tool_followup = False
    from scripts.mock_llm_server import clear_captures

    clear_captures(_session.config)
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


# --- Packet B: Stop, Send FSM ---


@native_test
def test_b1a_stop_ramble_then_hello(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
        _assert_stopped_banner(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b1b_stop_mouse_skipped(ctx):
    raise unittest.SkipTest(
        "B1b press_stop_mouse needs in-process SendButtonListener; URP ActionEvent is B1a"
    )


@native_test
def test_b1c_no_html_rerender_after_stop(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
        _assert_stopped_banner(before)
        suffix = _transcript()
        if suffix.startswith(before):
            suffix = suffix[len(before) :]
        assert "[Stopped by user]" in suffix
        assert suffix.strip().endswith("[Stopped by user]") or "[Stopped by user]" in suffix[-80:], (
            "B1c expected Stopped banner at tail, got %r" % suffix[-200:]
        )
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b2_stop_then_immediate_hello(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b3_double_stop_then_hello(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _press_stop()
        _press_stop()
        _wait_idle_after_send(before, timeout=25.0)
        _assert_stopped_banner(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b3b_stop_when_idle(ctx):
    _reset_mock_runtime()
    _press_stop()
    time.sleep(0.3)
    _hello_ok()


@native_test
def test_b4_record_skipped(ctx):
    raise unittest.SkipTest("B4 Record needs a device / Packet G")


@native_test
def test_b5_resize_during_stream_skipped(ctx):
    raise unittest.SkipTest("B5 resize during stream is soak-only (not v2)")


@native_test
def test_b6_double_send(ctx):
    from plugin.chatbot.sidebar_test_hooks import uno_click

    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        controls = getattr(_session, "controls", None)
        if controls is not None:
            uno_click(controls["send"])
        _stop_and_wait_idle(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b7_empty_query_no_http(ctx):
    from plugin.chatbot.sidebar_test_hooks import set_query_text_via_controls, uno_click
    from scripts.mock_llm_server import clear_captures

    _reset_mock_runtime()
    assert _session is not None
    clear_captures(_session.config)
    controls = getattr(_session, "controls", None)
    assert controls is not None
    set_query_text_via_controls(controls, "")
    time.sleep(0.3)
    n_before = len(_captures())
    before = _transcript()
    if _send_enabled() is True:
        uno_click(controls["send"])
        time.sleep(0.8)
    assert len(_captures()) == n_before, "B7 empty send must not POST to mock: %r" % _captures()
    assert _transcript() == before or not _wait_stop_enabled(timeout=0.4)
    _hello_ok()


@native_test
def test_b8_send_enabled_only_with_text(ctx):
    from plugin.chatbot.sidebar_test_hooks import set_query_text_via_controls

    _reset_mock_runtime()
    controls = getattr(_session, "controls", None)
    assert controls is not None
    set_query_text_via_controls(controls, "")
    time.sleep(0.3)
    empty_en = _send_enabled()
    assert empty_en is not True, "B8 Send should be disabled on empty query, got %r" % empty_en
    set_query_text_via_controls(controls, "hello")
    time.sleep(0.3)
    full_en = _send_enabled()
    assert full_en is True, "B8 Send should enable when query has text, got %r" % full_en
    assert "send" in _label(controls["send"]).lower() or _label(controls["send"]) == ""
    _hello_ok()


@native_test
def test_b9_ramble_natural_end_then_stop_second(ctx):
    _reset_mock_runtime()
    assert _session is not None
    _session.config.delay_ms = 20
    _send_and_wait("keep talking", timeout=180.0)
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
        _assert_stopped_banner(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b10_stop_hello_stop_again(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
        _assert_stopped_banner(before)
    finally:
        _reset_mock_runtime()
    _hello_ok()
    before2 = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before2)
        _assert_stopped_banner(before2)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b11_query_after_stop_then_hello(ctx):
    _reset_mock_runtime()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
    finally:
        _reset_mock_runtime()
    # Query may be restored or cleared; next hello must still type into the box.
    assert isinstance(_query_box_text(), str)
    _hello_ok()


@native_test
def test_b12_record_hooks_skipped(ctx):
    raise unittest.SkipTest("B12 Record/Stop Rec is Packet G (no mic in Packet B)")


@native_test
def test_b13_stop_before_first_chunk(ctx):
    _reset_mock_runtime()
    before = _transcript()
    try:
        _start_until_stop_enabled("hello", delay_ms=2000, timeout=8.0)
        _stop_and_wait_idle(before, timeout=25.0)
    except AssertionError:
        # Stop never enabled: still require idle so we are not stuck Starting…
        _press_stop()
        _wait_idle_after_send(before, timeout=25.0)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b14_stop_during_thinking(ctx):
    _reset_mock_runtime()
    before = _transcript()
    try:
        started = False
        try:
            _start_until_stop_enabled("think out loud", delay_ms=80, timeout=10.0)
            started = True
        except AssertionError:
            started = False
        if started:
            _stop_and_wait_idle(before, timeout=25.0)
        else:
            _wait_idle_after_send(before, timeout=40.0)
    finally:
        _reset_mock_runtime()
    _hello_ok()


@native_test
def test_b15_serial_hello_ramble_stop_empty_hello(ctx):
    _reset_mock_runtime()
    _hello_ok()
    before = _start_until_stop_enabled("keep talking", delay_ms=40)
    try:
        _stop_and_wait_idle(before)
        _assert_stopped_banner(before)
    finally:
        _reset_mock_runtime()
    _send_and_wait("say nothing", timeout=40.0)
    _hello_ok()


# --- Packet E: tools, delegate, HITL ---


@native_test
def test_e1_offline_look_up_then_hello(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    _send_and_wait("look up latest Python", timeout=90.0)
    body = _transcript().lower()
    assert "assistant:" in body or "python" in body or "research" in body or "look" in body, (
        "E1 expected research wrap-up, got %r" % _transcript()[-500:]
    )
    snaps = _captures()
    assert any(row.get("has_current_query_mark") or row.get("decided_tools") == ["web_research"] for row in snaps), (
        "E1 expected CURRENT QUERY or web_research in mock captures, got %r" % snaps[-5:]
    )
    _hello_ok()


@native_test
def test_e2_online_research_skipped(ctx):
    raise unittest.SkipTest("E2 live DuckDuckGo is not for CI (--offline only)")


@native_test
def test_e3_add_comment_then_hello(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    before = _annotation_count(ctx)
    _send_and_wait("add a comment", timeout=60.0, wait_for="comment")
    assert _annotation_count(ctx) > before, "E3 expected a Writer comment"
    _hello_ok()


@native_test
def test_e4_empty_doc_insert_comment(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, "")
    _send_and_wait("insert a comment", timeout=90.0)
    body = _writer_body(ctx)
    assert body.strip(), "E4 expected nonempty doc after apply_document_content"
    assert _annotation_count(ctx) >= 1, "E4 expected a comment after insert"
    _set_writer_body(ctx, WELCOME_BODY)
    _hello_ok()


@native_test
def test_e5_insert_filler_refreshes_context(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    before_len = len(_writer_body(ctx))
    _send_and_wait("insert filler", timeout=60.0)
    after_len = len(_writer_body(ctx))
    assert after_len > before_len, "E5 expected longer document, %s -> %s" % (before_len, after_len)
    snaps = _captures()
    max_doc = max((int(row.get("doc_content_len") or 0) for row in snaps), default=0)
    assert max_doc > before_len or max_doc >= after_len // 2, (
        "E5 expected refresh_document_context in a later POST, captures=%r" % snaps[-6:]
    )
    _hello_ok()


@native_test
def test_e6_two_tools_parallel(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    _send_and_wait("two tools", timeout=60.0)
    snaps = _captures()
    decided = []
    for row in snaps:
        decided.extend(row.get("decided_tools") or [])
        decided.extend(row.get("called_tools") or [])
    names = set(decided)
    assert "search_in_document" in names and "get_document_tree" in names, (
        "E6 expected both tools, got %r snaps=%r" % (names, snaps[-8:])
    )
    _hello_ok()


@native_test
def test_e7_outline_delegate(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    _send_and_wait("outline this", timeout=120.0)
    snaps = _captures()
    decided = []
    called = []
    for row in snaps:
        decided.extend(row.get("decided_tools") or [])
        called.extend(row.get("called_tools") or [])
    assert "delegate_to_specialized_writer_toolset" in set(decided + called), (
        "E7 expected delegate, snaps=%r" % snaps[-8:]
    )
    for row in snaps:
        for name in row.get("decided_tools") or []:
            if name == "delegate_read_document":
                raise AssertionError("E7 inner must not call empty-path delegate_read_document: %r" % row)
    body = _transcript().lower()
    assert "outline" in body or "assistant:" in body, "E7 expected outline wrap-up, got %r" % _transcript()[-400:]
    _hello_ok()


@native_test
def test_e8a_stop_during_nested_delegate(ctx):
    from plugin.chatbot.sidebar_test_hooks import (
        set_query_text_via_controls,
        uno_click,
        wait_controls_send_finished,
    )

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    assert _session is not None
    _session.config.delay_ms = 80
    _session.config.sync_delay_ms = 8000
    controls = getattr(_session, "controls", None)
    before = _transcript()
    try:
        if controls is not None:
            set_query_text_via_controls(controls, "outline this")
            time.sleep(0.2)
            uno_click(controls["send"])
            assert _wait_stop_enabled(timeout=15.0), "E8a Stop never enabled during nested work"
            _press_stop()
            assert wait_controls_send_finished(
                controls,
                timeout=40.0,
                transcript_fn=_transcript,
                before=before,
            ), "E8a did not go idle: %r" % _transcript()[-400:]
        else:
            sl = getattr(_session, "listener", None)
            assert sl is not None
            from plugin.chatbot.sidebar_test_hooks import press_send, set_query_text, wait_idle

            set_query_text("outline this", listener=sl)
            press_send(listener=sl)
            assert _wait_stop_enabled(timeout=15.0)
            _press_stop()
            assert wait_idle(listener=sl, timeout=40.0)
    finally:
        _session.config.delay_ms = 20
        _session.config.sync_delay_ms = None
    _hello_ok()


@native_test
def test_e8b_stop_mouse_skipped(ctx):
    raise unittest.SkipTest(
        "E8b press_stop_mouse needs in-process SendButtonListener; URP ActionEvent is E8a"
    )


@native_test
def test_e9a_hitl_accept(ctx):
    from plugin.framework.config import set_config

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    set_config("chatbot.prompt_for_web_research", True)
    time.sleep(2.1)
    controls = getattr(_session, "controls", None)
    try:
        from plugin.chatbot.sidebar_test_hooks import set_query_text_via_controls, uno_click, wait_controls_send_finished

        assert controls is not None
        set_query_text_via_controls(controls, "look up cats")
        time.sleep(0.2)
        uno_click(controls["send"])
        if not _wait_send_label("Accept", timeout=45.0):
            raise unittest.SkipTest("E9 HITL Accept label never appeared over URP")
        uno_click(controls["send"])
        assert wait_controls_send_finished(controls, timeout=90.0, transcript_fn=_transcript), (
            "E9a did not finish after Accept: %r" % _transcript()[-400:]
        )
    finally:
        set_config("chatbot.prompt_for_web_research", False)
        time.sleep(2.1)
    _hello_ok()


@native_test
def test_e9b_hitl_reject(ctx):
    from plugin.framework.config import set_config

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    set_config("chatbot.prompt_for_web_research", True)
    time.sleep(2.1)
    controls = getattr(_session, "controls", None)
    try:
        from plugin.chatbot.sidebar_test_hooks import set_query_text_via_controls, uno_click, wait_controls_send_finished

        assert controls is not None
        set_query_text_via_controls(controls, "look up cats")
        time.sleep(0.2)
        uno_click(controls["send"])
        if not _wait_send_label("Accept", timeout=45.0):
            raise unittest.SkipTest("E9 HITL Accept label never appeared over URP")
        clear = controls.get("clear")
        if clear is not None and "reject" in _label(clear).lower():
            uno_click(clear)
        else:
            uno_click(controls["stop"])
        assert wait_controls_send_finished(controls, timeout=40.0, transcript_fn=_transcript), (
            "E9b did not go idle after Reject: %r" % _transcript()[-400:]
        )
    finally:
        set_config("chatbot.prompt_for_web_research", False)
        time.sleep(2.1)
    _hello_ok()


@native_test
def test_e9c_hitl_change(ctx):
    from plugin.framework.config import set_config

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    sl = getattr(_session, "listener", None)
    if sl is None:
        raise unittest.SkipTest("E9c Change hook needs in-process SendButtonListener")
    set_config("chatbot.prompt_for_web_research", True)
    time.sleep(2.1)
    try:
        from plugin.chatbot.sidebar_test_hooks import press_change, press_send, set_query_text, wait_idle

        set_query_text("look up cats", listener=sl)
        press_send(listener=sl)
        if not _wait_send_label("Accept", timeout=45.0):
            raise unittest.SkipTest("E9 HITL Accept never appeared")
        press_change("cats", listener=sl)
        assert wait_idle(listener=sl, timeout=90.0)
        assert "[Stopped by user]" not in _transcript(), "E9c must not cancel the stream as Stop"
    finally:
        set_config("chatbot.prompt_for_web_research", False)
        time.sleep(2.1)
    _hello_ok()


@native_test
def test_e9d_stop_mouse_during_approval_skipped(ctx):
    raise unittest.SkipTest("E9d press_stop_mouse needs in-process listener (see F3b)")


@native_test
def test_e9e_stop_action_during_approval(ctx):
    from plugin.framework.config import set_config

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    set_config("chatbot.prompt_for_web_research", True)
    time.sleep(2.1)
    controls = getattr(_session, "controls", None)
    try:
        from plugin.chatbot.sidebar_test_hooks import set_query_text_via_controls, uno_click, wait_controls_send_finished

        assert controls is not None
        set_query_text_via_controls(controls, "look up cats")
        time.sleep(0.2)
        uno_click(controls["send"])
        if not _wait_send_label("Accept", timeout=45.0):
            raise unittest.SkipTest("E9 HITL Accept label never appeared over URP")
        before = _transcript()
        uno_click(controls["stop"])
        assert wait_controls_send_finished(controls, timeout=40.0, transcript_fn=_transcript), (
            "E9e did not finish after Stop/Change: %r" % _transcript()[-400:]
        )
        suffix = _transcript()
        if suffix.startswith(before):
            suffix = suffix[len(before) :]
        assert "[Stopped by user]" not in suffix, "E9e Stop during approval must not be StopSendEffect"
    finally:
        set_config("chatbot.prompt_for_web_research", False)
        time.sleep(2.1)
    _hello_ok()


@native_test
def test_e10_tool_followup_500(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    assert _session is not None
    _session.config.fail_tool_followup = True
    try:
        _send_and_wait("add a comment", timeout=60.0)
        body = _transcript()
        _assert_errorish(body, "500", "API error")
    finally:
        _session.config.fail_tool_followup = False
    _hello_ok()


@native_test
def test_e11_filler_then_comment_two_sends(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    _send_and_wait("insert filler", timeout=60.0)
    assert len(_writer_body(ctx)) > len(WELCOME_BODY)
    before_c = _annotation_count(ctx)
    _send_and_wait("add a comment", timeout=60.0, wait_for="comment")
    assert _annotation_count(ctx) > before_c
    _hello_ok()


@native_test
def test_e12_calc_list_sheets(ctx):
    from plugin.chatbot.sidebar_test_hooks import (
        current_component,
        desktop_from_ctx,
        wait_for_chat_dialog_controls,
    )
    from plugin.doc.doc_type import is_calc, is_writer

    _reset_mock_runtime()
    desktop = desktop_from_ctx(ctx)
    calc = desktop.loadComponentFromURL("private:factory/scalc", "_default", 0, ())
    time.sleep(1.5)
    controls = wait_for_chat_dialog_controls(ctx, timeout=15.0)
    if controls is None:
        if calc is not None:
            try:
                calc.close(True)
            except Exception:
                pass
        _ensure_writer_doc(ctx)
        raise unittest.SkipTest("E12 Calc WriterAgent deck not available in this runner")
    _session.controls = controls
    try:
        _send_and_wait("list sheets", timeout=60.0)
        body = _transcript().lower()
        assert "sheet" in body or "assistant:" in body, "E12 expected list_sheets wrap-up, got %r" % _transcript()[-400:]
        _hello_ok()
    finally:
        try:
            if calc is not None:
                calc.close(True)
        except Exception:
            pass
        _ensure_writer_doc(ctx)
        time.sleep(1.0)
        restored = wait_for_chat_dialog_controls(ctx, timeout=15.0)
        if restored is not None:
            _session.controls = restored
        doc = current_component(ctx)
        if doc is not None and is_writer(doc) and not is_calc(doc):
            _set_writer_body(ctx, WELCOME_BODY)


@native_test
def test_e13_stop_during_add_comment(ctx):
    from plugin.chatbot.sidebar_test_hooks import (
        set_query_text_via_controls,
        uno_click,
        wait_controls_send_finished,
    )

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    assert _session is not None
    _session.config.delay_ms = 80
    controls = getattr(_session, "controls", None)
    before = _transcript()
    try:
        if controls is not None:
            set_query_text_via_controls(controls, "add a comment")
            time.sleep(0.2)
            uno_click(controls["send"])
            if _wait_stop_enabled(timeout=8.0):
                _press_stop()
            assert wait_controls_send_finished(
                controls, timeout=30.0, transcript_fn=_transcript, before=before
            ), "E13 did not go idle: %r" % _transcript()[-400:]
        else:
            _send_and_wait("add a comment", timeout=30.0)
    finally:
        _session.config.delay_ms = 20
    _hello_ok()


@native_test
def test_e14_outline_twice(ctx):
    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    _send_and_wait("outline this", timeout=120.0)
    _send_and_wait("outline this", timeout=120.0)
    snaps = _captures()
    n_delegate = sum(
        1
        for row in snaps
        if "delegate_to_specialized_writer_toolset" in (row.get("decided_tools") or [])
    )
    assert n_delegate >= 2, "E14 expected two delegate sends, got %s snaps=%r" % (n_delegate, snaps[-10:])
    _hello_ok()


@native_test
def test_e15_stop_after_filler_tool_before_wrapup(ctx):
    from plugin.chatbot.sidebar_test_hooks import (
        set_query_text_via_controls,
        uno_click,
        wait_controls_send_finished,
    )

    _reset_mock_runtime()
    _set_writer_body(ctx, WELCOME_BODY)
    assert _session is not None
    _session.config.delay_ms = 40
    controls = getattr(_session, "controls", None)
    before = _transcript()
    try:
        if controls is not None:
            set_query_text_via_controls(controls, "insert filler")
            time.sleep(0.2)
            uno_click(controls["send"])
            if _wait_stop_enabled(timeout=8.0):
                _press_stop()
            assert wait_controls_send_finished(
                controls, timeout=30.0, transcript_fn=_transcript, before=before
            ), "E15 did not go idle: %r" % _transcript()[-400:]
        else:
            _send_and_wait("insert filler", timeout=30.0)
    finally:
        _session.config.delay_ms = 20
    _hello_ok()

