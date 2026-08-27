# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Lightweight synchronous event bus for inter-module communication."""

import sys
import logging
import threading
import weakref

from plugin.framework.service import ServiceBase

log = logging.getLogger("writeragent.events")


from plugin.framework.deal_shim import deal


class EventBus:
    """Publish/subscribe event bus.

    All callbacks run synchronously on the calling thread. Exceptions in
    subscribers are logged but never propagated to the emitter.

    Re-entrant ``emit`` of the *same* event on the same thread is dropped
    (warning logged). That stops the sidebar config-refresh loop where
    ``config:changed`` → control ``setText`` → listener → ``set_config`` →
    ``config:changed`` again. Nested *different* events still run. Concurrent
    emits of the same name on *other* threads are not dropped (thread-local
    dispatch set, not a process-wide lock).

    Usage::

        bus = EventBus()
        bus.subscribe("config:changed", my_callback)
        bus.emit("config:changed", key="mcp.port", value=9000)

    Weak references are supported to avoid preventing garbage collection
    of listener objects::

        bus.subscribe("document:closed", obj.on_close, weak=True)
    """

    def __init__(self):
        self._subscribers = {}  # event -> list of (callback, is_weakref)
        # Per-thread names currently in emit(); instance-wide would drop
        # legitimate parallel emits of the same event from two threads.
        self._dispatching = threading.local()

    def subscribe(self, event, callback, weak=False):
        """Register *callback* for *event*.

        Args:
            event:    Event name (e.g. "config:changed").
            callback: Callable to invoke when the event is emitted.
            weak:     If True, store a weakref to the callback's bound
                      object. The subscription auto-removes when the
                      object is garbage-collected.
        """
        if event not in self._subscribers:
            self._subscribers[event] = []

        if weak:
            if hasattr(callback, "__self__"):
                ref = weakref.WeakMethod(callback, lambda r: self._cleanup(event, r))
                self._subscribers[event].append((ref, True))
            else:
                try:
                    ref = weakref.ref(callback, lambda r: self._cleanup(event, r))
                    self._subscribers[event].append((ref, True))
                except TypeError:
                    self._subscribers[event].append((callback, False))
        else:
            self._subscribers[event].append((callback, False))

    def unsubscribe(self, event, callback):
        """Remove *callback* from *event*."""
        subs = self._subscribers.get(event)
        if not subs:
            return

        self._subscribers[event] = [
            (cb, is_weak) for cb, is_weak in subs if not self._same_callback(self._resolve(cb, is_weak), callback)
        ]

    @staticmethod
    def _same_callback(stored, callback):
        """True if *stored* is the same callable the caller passed.

        Bound methods are new objects on every attribute access
        (``obj.m is obj.m`` is False), so identity alone never matches
        ``unsubscribe("e", obj.handler)``. Compare ``__self__``/``__func__``.
        """
        if stored is None:
            return False
        if stored is callback:
            return True
        stored_self = getattr(stored, "__self__", None)
        other_self = getattr(callback, "__self__", None)
        if stored_self is None or other_self is None:
            return False
        return stored_self is other_self and getattr(stored, "__func__", None) is getattr(callback, "__func__", None)

    def _active_events(self) -> set:
        active = getattr(self._dispatching, "events", None)
        if active is None:
            active = set()
            self._dispatching.events = active
        return active

    @deal.post(lambda result: result is None)
    def emit(self, event, **data):
        """Emit *event*, calling all subscribers with **data as kwargs.

        Exceptions in subscribers are logged and swallowed.
        Re-entrant emit of the same event on this thread is dropped.
        """
        # crosshair: off
        subs = self._subscribers.get(event)
        if not subs:
            return

        active = self._active_events()
        if event in active:
            log.warning("Suppressed re-entrant event_bus.emit for %r on the same thread", event)
            return

        active.add(event)
        try:
            dead = []
            for i, (cb, is_weak) in enumerate(subs):
                resolved = self._resolve(cb, is_weak)
                if resolved is None:
                    dead.append(i)
                    continue
                try:
                    resolved(**data)
                except TypeError:
                    log.exception("TypeError in event handler %s for %s", resolved, event)
                except ValueError:
                    log.exception("ValueError in event handler %s for %s", resolved, event)
                except Exception as e:
                    # Still catch Exception to avoid one bad listener breaking the whole bus,
                    # but log it clearly as an unhandled application error
                    log.exception("Unhandled error in event handler %s for %s: %s", resolved, event, e)

            if dead:
                for i in reversed(dead):
                    subs.pop(i)
        finally:
            active.discard(event)

    def _resolve(self, cb, is_weak):
        if is_weak:
            return cb()  # weakref -> call to dereference
        return cb

    def _cleanup(self, event, ref):
        """Called when a weakref target is garbage-collected."""
        subs = self._subscribers.get(event)
        if subs:
            self._subscribers[event] = [(cb, w) for cb, w in subs if cb is not ref]


def get_event_bus():
    """Return the true singleton EventBus across all LO import contexts."""
    if not hasattr(sys, "_writeragent_event_bus"):
        setattr(sys, "_writeragent_event_bus", EventBus())
    return getattr(sys, "_writeragent_event_bus")


global_event_bus = get_event_bus()


class EventBusService(ServiceBase, EventBus):
    """Singleton event bus exposed as a service.

    Inherits from both ServiceBase (for registry) and EventBus (for
    pub/sub). Modules access it as ``services.events``.
    """

    name = "events"

    def __init__(self):
        ServiceBase.__init__(self)
        # Share the process-wide subscriber dict; do not reassign this attribute
        # or the service would silently desync from global_event_bus.
        self._subscribers = global_event_bus._subscribers
        self._dispatching = global_event_bus._dispatching
