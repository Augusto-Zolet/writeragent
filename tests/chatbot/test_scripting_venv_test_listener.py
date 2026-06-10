"""Settings → Python Test shows a modal dialog with incremental probe output."""

from unittest.mock import MagicMock, patch

from plugin.chatbot.dialog_views import ScriptingVenvTestListener, _dialog_parent_for_child


def test_python_test_uses_modal_incremental_probe() -> None:
    order: list[str] = []
    fake_ctx = MagicMock()
    fake_dlg = MagicMock()
    probe_displays: list[str] = []
    probe_statuses: list[str] = []

    class _FakeProgress:
        def __init__(self, ctx, parent_dlg=None):
            order.append("progress_ctor")
            assert parent_dlg is fake_dlg

        def run_modal_probe(self, probe_fn):
            order.append("progress_run_modal")
            probe_fn(probe_displays.append, probe_statuses.append)
            return True

    def fake_probe(_raw, on_display, on_status=None, extra_lines_after_header=None):
        on_display("Python 3.12 responds OK.\nCython Accelerator: Inactive (Pure Python)\n\nScientific Libraries:\n  Present: numpy\n  Missing: pandas")
        if on_status:
            on_status("Scientific Libraries: numpy")
        return True, "Python 3.12 responds OK."

    listener = ScriptingVenvTestListener(fake_ctx, fake_dlg)
    with (
        patch("plugin.chatbot.dialog_views.get_optional", return_value=None),
        patch("plugin.chatbot.dialog_views._VenvProbeProgressDialog", _FakeProgress),
        patch("plugin.scripting.venv_worker.probe_venv_path_with_progress", side_effect=fake_probe),
        patch("plugin.scripting.payload_codec.fast_flatten_grid_2d", None),
    ):
        listener.on_action_performed(MagicMock())

    assert "progress_run_modal" in order
    assert any("Present:" in text for text in probe_displays)
    assert any("Cython Accelerator" in text for text in probe_displays)
    assert any("numpy" in status for status in probe_statuses)


def test_dialog_parent_for_child_prefers_settings_peer() -> None:
    parent = MagicMock()
    parent.getPeer.return_value = "settings-peer"
    assert _dialog_parent_for_child(MagicMock(), parent) == "settings-peer"
    parent.getPeer.assert_called_once()
