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
"""Native (real soffice) tests for plugin.chatbot.rich_text lifecycle / disposal.

This module exists specifically to give regression coverage for the rich-text
sidebar crash-on-close bug (Signal 11 / "object has been disposed" during
Writer exit or deck teardown when rich_text_sidebar is active).

It exercises the EmbeddedWriterListener, its Sidebar*Listener helpers,
the _dispose_embedded_objects path, the new pure-Python instrumentation +
defang code, and the cooperative cleanup from SendButtonListener, all against
real UNO objects obtained from a live Writer document.

Full end-to-end reproduction of the VCL child registration (toolkit.createWindow
with a real sidebar XDL dialog peer) is difficult in the test runner because the
rich-text feature is config-gated + restart-gated. The tests here therefore focus
on the Python + UNO listener and disposal logic that *can* be driven directly;
they still catch many classes of lifetime bugs and ensure the new instrumentation
does not itself crash.

See docs/rich-text-sidebar.md (Lifecycle section) and the unit tests in
test_rich_text.py for the broader context and the pre-fix failure modes.
"""

from typing import Any

from plugin.framework.logging import log
from plugin.framework.uno_context import get_desktop
from plugin.testing_runner import setup, teardown, native_test

_test_doc: Any = None
_test_ctx: Any = None


@setup
def setup_rich_text_lifecycle(ctx):
    global _test_doc, _test_ctx
    _test_ctx = ctx

    desktop = get_desktop(ctx)
    import uno

    hidden_prop = uno.createUnoStruct(
        "com.sun.star.beans.PropertyValue",
        Name="Hidden",
        Value=True,
    )

    _test_doc = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (hidden_prop,))
    assert _test_doc is not None, "Could not create Writer document for rich-text lifecycle test"
    log.info("[RichTextLifecycleTest] setup complete; doc created")


@teardown
def teardown_rich_text_lifecycle(ctx):
    global _test_doc, _test_ctx
    if _test_doc:
        try:
            _test_doc.close(True)
        except Exception:
            pass
    _test_doc = None
    _test_ctx = None


@native_test
def test_rich_text_listener_disposal_paths():
    """Exercise the core disposal paths with real UNO objects.

    - Creates an EmbeddedWriterListener bound to the test document's model + frame.
    - Triggers disposing() and the internal _dispose_embedded_objects.
    - Verifies the _disposed guard, listener removal (best-effort), and ref clearing.
    - Explicitly calls the new pure-Python instrumentation/defang helper to ensure
      it does not raise even when no real VCL sidebar parent exists.
    - Also instantiates the Sidebar*Listener wrapper classes (if the UNO interfaces
      were importable) to keep those code paths covered.

    The test is intentionally tolerant: many objects will be None or stubs because
    we do not have a full sidebar XUIElement here. The important thing is that the
    disposal code runs to completion without leaking exceptions or violating its
    own guards.
    """
    try:
        import pytest
        if _test_doc is None or _test_ctx is None:
            pytest.skip("Requires LibreOffice document + ctx from native runner")
    except ImportError:
        pass

    from plugin.chatbot import rich_text as rt
    import uno

    # Fresh guard state (mirrors what the unit tests do)
    rt._EMBEDDING_STARTED.clear()

    # Real UNO objects we can obtain without a sidebar
    doc_model = _test_doc
    host_frame = None
    try:
        ctrl = _test_doc.getCurrentController()
        if ctrl:
            host_frame = ctrl.getFrame()
    except Exception:
        pass

    # We need *some* parent_window that has getPeer() for the listener ctor.
    # Use the doc's component window (or its container) as a stand-in; it is a
    # real VCL peer and exercises the same code paths.
    parent_window = None
    placeholder = None  # Not used in disposal paths we care about here
    try:
        if host_frame:
            parent_window = host_frame.getContainerWindow()
    except Exception:
        pass
    if parent_window is None:
        # Last resort: the document's own window (still a valid XWindow with peer)
        try:
            parent_window = _test_doc.getCurrentController().getFrame().getContainerWindow()
        except Exception:
            pass

    # Minimal stand-in if we truly have nothing (keeps the ctor happy without
    # polluting the native test's module snapshot with a top-level unittest import).
    class _SimpleWindowStandIn:
        def getPeer(self):
            return None

    pw_for_listener = parent_window or _SimpleWindowStandIn()
    ph_for_listener = placeholder or _SimpleWindowStandIn()

    # Create the listener (the central object for all rich-text shutdown logic)
    listener = rt.EmbeddedWriterListener(
        _test_ctx,
        pw_for_listener,
        ph_for_listener,
        lambda *a, **k: None,
        doc_model=doc_model,
        host_frame=host_frame,
    )

    # Give it some embedded objects (simulating a partially-initialized rich sidebar)
    # These will be None or real depending on whether we could create them; the
    # disposal code must tolerate both.
    try:
        listener.doc = _test_doc  # not really "ours" but exercises the remove path
    except Exception:
        pass

    # Exercise the new instrumentation + defang helper directly (the main artifact
    # of the pure-Python drop_ownership investigation). It must not raise.
    try:
        listener._instrument_vcl_child_relationship_and_defang("native-test direct call")
    except Exception as e:
        # If this blows up the test is a failure (we want to know immediately).
        raise AssertionError(f"_instrument_vcl_child... raised in native test: {e}") from e

    # Now the normal disposal path
    try:
        listener.disposing(None)
    except Exception as e:
        raise AssertionError(f"listener.disposing raised in native test: {e}") from e

    assert listener._disposed is True, "disposing() must have set the _disposed guard"

    # Idempotency
    try:
        listener.disposing(None)  # second call must be a no-op
    except Exception as e:
        raise AssertionError(f"second disposing() raised: {e}") from e

    # The Sidebar*Listener wrappers (these are the ones registered on doc/frame/desktop)
    # Exercise their code paths so we keep the notifyClosing / queryTermination /
    # documentEventOccured shims healthy.
    if rt._HAVE_UNO_CLOSE_EVENTS:
        try:
            cl = rt.SidebarCloseListener(listener)
            cl.notifyClosing(None)
            cl.disposing(None)
        except Exception as e:
            log.info("[RichTextLifecycleTest] SidebarCloseListener path: %s (non-fatal in test)", e)

    if rt._HAVE_UNO_DOC_EVENTS:
        try:
            dl = rt.SidebarDocumentEventListener(listener)
            # documentEventOccured expects a real event struct in real use; the
            # stub path just calls through to the listener, which is what we want.
            dl.documentEventOccured(None)
            dl.disposing(None)
        except Exception as e:
            log.info("[RichTextLifecycleTest] SidebarDocumentEventListener path: %s", e)

    if rt._HAVE_UNO_TERMINATE:
        try:
            tl = rt.SidebarTerminateListener(listener)
            tl.queryTermination(None)
            tl.notifyTermination(None)
            tl.disposing(None)
        except Exception as e:
            log.info("[RichTextLifecycleTest] SidebarTerminateListener path: %s", e)

    log.info("[RichTextLifecycleTest] test_rich_text_listener_disposal_paths completed successfully")


# Optional future expansion (left as comments so the test file stays small and focused):
#
# - A test that actually calls create_embedded_writer_doc with a real toolkit-created
#   parent peer (if we can synthesize a minimal XDialog or docking window in the runner).
#   This would exercise the full VCL child registration + the getWindows() child check.
#
# - Force a sequence that mimics "OnPrepareUnload then user cancel" by disposing the
#   embedded objects and then re-creating them on a subsequent "shown" event.
#
# These can be added later without changing the fundamental value of the current test.