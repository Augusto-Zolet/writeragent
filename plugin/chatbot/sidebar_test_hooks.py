# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Debug-only sidebar hooks for mock-LLM native tests.

Release OXTs replace this module with a stub (see ``scripts/strip_code.py``).
Do not synthesize clicks: drive the same listeners as the widgets.

See docs/chat/rich-text-control-sidebar.md (Hooks).
"""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable
from weakref import WeakSet

from plugin.chatbot.panel import StopButtonListener, notify_stop_mouse_pressed
from plugin.chatbot.send_state import SendEvent, SendEventKind

log = logging.getLogger("writeragent.sidebar_test_hooks")

_HOOKS_UNAVAILABLE = "sidebar test hooks are not in release builds"

# Debug-only. This module is replaced by a stub in release OXTs (no WeakSet).
_LIVE_CHAT_PANELS: WeakSet[Any] = WeakSet()


def register_live_panel(element: Any) -> None:
    _require_debug()
    if element is not None:
        _LIVE_CHAT_PANELS.add(element)


def unregister_live_panel(element: Any) -> None:
    _require_debug()
    _LIVE_CHAT_PANELS.discard(element)


def iter_live_chat_panels() -> list[Any]:
    _require_debug()
    return list(_LIVE_CHAT_PANELS)


def debug_hooks_available() -> bool:
    """False when ``thread_guard`` is the release stub (no ``_designated_main_thread``)."""
    try:
        from plugin.framework import thread_guard as tg

        return hasattr(tg, "_designated_main_thread")
    except Exception:
        return False


def _require_debug() -> None:
    if not debug_hooks_available():
        raise RuntimeError(_HOOKS_UNAVAILABLE)


def sidebar_panel(frame: Any = None) -> Any:
    """Return the live ``ChatPanelElement`` for *frame*, or the only live panel."""
    _require_debug()
    panels = iter_live_chat_panels()
    if not panels:
        return None
    if frame is not None:
        for panel in panels:
            if getattr(panel, "xFrame", None) is frame or getattr(panel, "Frame", None) is frame:
                return panel
    if len(panels) == 1:
        return panels[0]
    return panels[0]


def send_listener(frame: Any = None) -> Any:
    _require_debug()
    panel = sidebar_panel(frame)
    if panel is None:
        return None
    return getattr(panel, "send_listener", None)


def _control_label(control: Any) -> str:
    try:
        model = control.getModel() if control is not None else None
        if model is not None:
            return str(getattr(model, "Label", "") or "")
    except Exception:
        log.debug("control label read failed", exc_info=True)
    return ""


def set_query_text(text: str, *, listener: Any = None) -> None:
    """Set the query box and dispatch ``TEXT_UPDATED`` (same as ``QueryTextListener``)."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    from plugin.chatbot.dialogs import set_control_text

    query = getattr(sl, "query_control", None)
    set_control_text(query, text)
    stripped = (text or "").strip()
    sl.dispatch(SendEvent(SendEventKind.TEXT_UPDATED, {"has_text": bool(stripped)}))


def query_text(*, listener: Any = None) -> str:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        return ""
    from plugin.chatbot.dialogs import get_control_text

    return get_control_text(getattr(sl, "query_control", None), default="") or ""


def transcript_text(*, listener: Any = None) -> str:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        return ""
    from plugin.chatbot.dialogs import get_control_text

    widget = getattr(sl, "rich_text_widget", None)
    control = getattr(widget, "control", None) if widget is not None else None
    if control is None:
        control = getattr(sl, "response_control", None)
    return get_control_text(control, default="") or ""


def transcript_contains(needle: str, *, listener: Any = None) -> bool:
    _require_debug()
    return needle in transcript_text(listener=listener)


def press_send(*, listener: Any = None) -> None:
    """Primary Send button path (also Accept when HITL owns the label)."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    sl.on_action_performed(None)


def press_stop(*, listener: Any = None) -> None:
    """Windows / ActionEvent Stop path (``StopButtonListener.on_action_performed``)."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    StopButtonListener(sl).on_action_performed(None)


def press_stop_mouse(*, listener: Any = None) -> None:
    """GTK Stop ``mousePressed`` path. No-op while web-search approval is active."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    notify_stop_mouse_pressed(sl)


def press_accept(*, listener: Any = None) -> None:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    sl.on_action_performed(None)


def press_change(query_override: str | None = None, *, listener: Any = None) -> None:
    """HITL Change without the modal edit dialog (Packet E9c). Not ``STOP_CLICKED``."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    if query_override is None:
        query_override = getattr(sl, "_approval_query_for_engine", None) or ""
    sl._finish_inline_web_approval(True, query_override=query_override)


def press_reject(*, listener: Any = None) -> None:
    """HITL Reject (Clear-button overlay). Not ``STOP_CLICKED``."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    sl._finish_inline_web_approval(False)


def approval_active(*, listener: Any = None) -> bool:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        return False
    return getattr(sl, "_approval_event", None) is not None


def press_record(*, listener: Any = None) -> None:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    sl.dispatch(SendEvent(SendEventKind.RECORD_CLICKED))


def press_stop_rec(*, listener: Any = None) -> None:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    sl.dispatch(SendEvent(SendEventKind.STOP_REC_CLICKED))


def set_audio_supported(supported: bool, *, listener: Any = None) -> None:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    ss = sl.sidebar_state
    send = dataclasses.replace(ss.send, audio_supported=bool(supported))
    sl.sidebar_state = dataclasses.replace(ss, send=send)
    sl.dispatch(
        SendEvent(
            SendEventKind.TEXT_UPDATED,
            {"has_text": bool(send.has_text)},
        )
    )


def audio_status(*, listener: Any = None) -> dict[str, Any]:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        return {"status": "idle", "has_audio": False}
    send = sl.sidebar_state.send
    audio = sl.sidebar_state.audio
    return {
        "status": getattr(audio, "status", "idle"),
        "has_audio": bool(send.has_audio),
        "is_recording": bool(send.is_recording),
        "error_message": getattr(audio, "error_message", None),
    }


def inject_wav(path_or_bytes: Any) -> None:
    _require_debug()
    raise NotImplementedError("inject_wav is reserved for Packet G (no mic)")


def stub_recorder_child() -> None:
    _require_debug()
    raise NotImplementedError("stub_recorder_child is reserved for Packet G (no mic)")


@dataclass(frozen=True)
class SidebarHookSendView:
    is_busy: bool
    is_recording: bool
    has_text: bool
    has_audio: bool
    audio_supported: bool
    send_label: str
    stop_label: str


def send_state(*, listener: Any = None) -> SidebarHookSendView:
    _require_debug()
    sl = listener if listener is not None else send_listener()
    if sl is None:
        raise RuntimeError("no live SendButtonListener")
    send = sl.sidebar_state.send
    return SidebarHookSendView(
        is_busy=bool(send.is_busy),
        is_recording=bool(send.is_recording),
        has_text=bool(send.has_text),
        has_audio=bool(send.has_audio),
        audio_supported=bool(send.audio_supported),
        send_label=_control_label(getattr(sl, "send_control", None)),
        stop_label=_control_label(getattr(sl, "stop_control", None)),
    )


def pump_until(pred: Callable[[], bool], timeout: float = 30.0, *, ctx: Any = None) -> bool:
    """Idle-pump until *pred* is true. Uses ``force=True`` so native tests still pump VCL."""
    _require_debug()
    from plugin.framework.uno_context import get_ctx, process_events_to_idle

    deadline = time.monotonic() + max(0.0, timeout)
    uno_ctx = ctx
    if uno_ctx is None:
        sl = send_listener()
        uno_ctx = getattr(sl, "ctx", None) if sl is not None else None
        if uno_ctx is None:
            try:
                uno_ctx = get_ctx()
            except Exception:
                uno_ctx = None
    while time.monotonic() <= deadline:
        if pred():
            return True
        if uno_ctx is not None:
            process_events_to_idle(uno_ctx, rounds=1, force=True)
        else:
            time.sleep(0.01)
    return pred()


def wait_idle(*, listener: Any = None, timeout: float = 30.0) -> bool:
    _require_debug()

    def _idle() -> bool:
        sl = listener if listener is not None else send_listener()
        if sl is None:
            return False
        send = sl.sidebar_state.send
        return (not send.is_busy) and (not send.is_recording)

    ctx = getattr(listener, "ctx", None) if listener is not None else None
    return pump_until(_idle, timeout, ctx=ctx)


def next_hello_ok(*, listener: Any = None, timeout: float = 60.0) -> bool:
    """Send ``hello``, wait until idle, require assistant HTML or hello text in the transcript."""
    _require_debug()
    sl = listener if listener is not None else send_listener()
    set_query_text("hello", listener=sl)
    press_send(listener=sl)
    if not wait_idle(listener=sl, timeout=timeout):
        return False
    text = transcript_text(listener=sl).lower()
    if "hello" in text or "<p" in text or "<ul" in text or "<ol" in text:
        return True
    log.warning("next_hello_ok: idle but transcript did not look like a hello reply")
    return False
