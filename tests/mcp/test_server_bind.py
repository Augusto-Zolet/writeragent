# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP/MCP bind: single attempt, clear failure — no LibreOffice required."""
import socket

import pytest

from plugin.mcp.server import (
    HttpServer,
    _PORT_IN_USE_GUIDANCE,
    format_mcp_start_failure,
    is_port_in_use_error,
)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _EmptyRoutes:
    route_count = 0


def test_start_binds_on_free_port():
    srv = HttpServer(route_registry=_EmptyRoutes(), port=_free_port(), host="127.0.0.1")
    srv.start()
    try:
        assert srv.is_running()
    finally:
        srv.stop()


def test_start_raises_immediately_when_port_busy(monkeypatch):
    # Persistent holder — must not sleep/retry (used to block LO bootstrap ~4s).
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupier.bind(("127.0.0.1", 0))
    occupier.listen(1)
    port = occupier.getsockname()[1]

    sleeps = {"n": 0}
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: sleeps.__setitem__("n", sleeps["n"] + 1))

    try:
        srv = HttpServer(route_registry=_EmptyRoutes(), port=port, host="127.0.0.1")
        with pytest.raises(OSError):
            srv.start()
        assert sleeps["n"] == 0
    finally:
        occupier.close()

def test_is_port_in_use_error_by_errno():
    assert is_port_in_use_error(OSError(98, "Address already in use"))
    assert is_port_in_use_error(OSError(48, "Address already in use"))
    err = OSError("busy")
    err.winerror = 10048
    assert is_port_in_use_error(err)
    assert not is_port_in_use_error(OSError(13, "Permission denied"))
    assert not is_port_in_use_error(RuntimeError("boom"))


def test_format_mcp_start_failure_port_in_use():
    msg = format_mcp_start_failure("localhost", 18765, OSError(98, "Address already in use"))
    assert "localhost:18765" in msg
    assert "OSError" in msg
    assert _PORT_IN_USE_GUIDANCE in msg
    assert "mcp.mcp_port" in msg


def test_format_mcp_start_failure_other_oserror():
    msg = format_mcp_start_failure("127.0.0.1", 9000, OSError(13, "Permission denied"))
    assert "127.0.0.1:9000" in msg
    assert "Permission denied" in msg
    assert _PORT_IN_USE_GUIDANCE not in msg


def test_start_server_stashes_last_start_error(monkeypatch):
    """Failed HttpServer.start must leave a reason for Toggle/Status (#379)."""
    import threading
    from unittest.mock import MagicMock

    import plugin.mcp as mcp_mod

    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)

    services = MagicMock()
    proxy = MagicMock()
    proxy.get.side_effect = lambda k, d=None: {
        "mcp_port": 18765,
        "host": "localhost",
        "use_ssl": False,
        "ssl_cert": "",
        "ssl_key": "",
    }.get(k, d)
    services.config.proxy_for.return_value = proxy
    services.events = None

    mod = mcp_mod.McpModule.__new__(mcp_mod.McpModule)
    mod._registry = MagicMock()
    mod._srv_lock = threading.Lock()
    mod._server = None
    mod.name = "mcp"

    boom = OSError(98, "Address already in use")

    class _FailingServer:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise boom

        def stop(self):
            pass

    monkeypatch.setattr(mcp_mod, "_shared_http_server", None)
    monkeypatch.setattr("plugin.mcp.server.HttpServer", _FailingServer)
    monkeypatch.setattr("plugin.mcp.reload_cors_policy_from_config", lambda *_a, **_k: None)

    assert mod._start_server(services) is False
    assert mcp_mod._last_start_error is boom
    detail = mod._formatted_start_failure()
    assert "localhost:18765" in detail
    assert _PORT_IN_USE_GUIDANCE in detail
    assert mod._start_failure_reportable() is False
