"""Unit tests for plugin.testing_runner LibreOffice shutdown."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.testing_runner import _shutdown_libreoffice


def test_shutdown_skips_process_events_to_idle_when_not_show_window() -> None:
    ctx = MagicMock()
    smgr = ctx.getServiceManager.return_value
    desktop = MagicMock()
    toolkit = MagicMock()
    smgr.createInstanceWithContext.side_effect = lambda name, _ctx: {
        "com.sun.star.frame.Desktop": desktop,
        "com.sun.star.awt.Toolkit": toolkit,
    }[name]

    with patch("plugin.testing_runner.show_window", False):
        _shutdown_libreoffice(ctx)

    toolkit.processEventsToIdle.assert_not_called()
    desktop.terminate.assert_called_once()


def test_shutdown_pumps_idle_when_show_window() -> None:
    ctx = MagicMock()
    smgr = ctx.getServiceManager.return_value
    desktop = MagicMock()
    toolkit = MagicMock()
    smgr.createInstanceWithContext.side_effect = lambda name, _ctx: {
        "com.sun.star.frame.Desktop": desktop,
        "com.sun.star.awt.Toolkit": toolkit,
    }[name]

    with patch("plugin.testing_runner.show_window", True):
        _shutdown_libreoffice(ctx)

    toolkit.processEventsToIdle.assert_called_once()
    desktop.terminate.assert_called_once()
