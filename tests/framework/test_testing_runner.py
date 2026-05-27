"""Unit tests for plugin.testing_runner LibreOffice shutdown helpers."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from plugin.testing_runner import (
    _DESKTOP_TERMINATE_TIMEOUT_SEC,
    _force_kill_libreoffice,
    _terminate_desktop_with_timeout,
)


def test_terminate_desktop_with_timeout_completes_without_force_kill() -> None:
    desktop = MagicMock()
    with patch("plugin.testing_runner._force_kill_libreoffice") as kill:
        _terminate_desktop_with_timeout(desktop, timeout=1.0)
    desktop.terminate.assert_called_once()
    kill.assert_not_called()


def test_terminate_desktop_with_timeout_force_kills_when_terminate_hangs() -> None:
    desktop = MagicMock()
    started = threading.Event()

    def hang() -> None:
        started.set()
        time.sleep(30)

    desktop.terminate.side_effect = hang
    with patch("plugin.testing_runner._force_kill_libreoffice") as kill:
        _terminate_desktop_with_timeout(desktop, timeout=0.2)
    assert started.wait(timeout=1.0)
    kill.assert_called_once()


def test_terminate_desktop_default_timeout_is_ten_seconds() -> None:
    assert _DESKTOP_TERMINATE_TIMEOUT_SEC == 10.0


@patch("sys.platform", "linux")
@patch("os.kill")
@patch("subprocess.run")
def test_force_kill_libreoffice_sends_sigkill(mock_run, mock_kill) -> None:
    mock_run.return_value = MagicMock(stdout="1234 5678\n", returncode=0)
    _force_kill_libreoffice()
    assert mock_run.call_count == len(("soffice", "soffice.bin", "oosplash"))
    mock_kill.assert_any_call(1234, 9)
    mock_kill.assert_any_call(5678, 9)
