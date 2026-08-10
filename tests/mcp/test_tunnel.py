"""Unit tests for the lightweight multi-provider MCP tunnel helper."""

from unittest.mock import MagicMock, patch

from plugin.mcp.tunnel import (
    TunnelManager,
    _redact_cmd_for_log,
    build_bore_command,
    build_cloudflare_command,
    build_ngrok_command,
    build_tailscale_command,
    detect_tunnel_auth_error,
    normalize_public_base,
    parse_bore_provider_config,
    parse_bore_url,
    parse_cloudflare_url,
    parse_ngrok_url,
    parse_tailscale_url,
    provider_label,
)


def test_build_cloudflare_quick_and_token():
    assert build_cloudflare_command(18765) == [
        "cloudflared",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://localhost:18765",
    ]
    assert build_cloudflare_command(18765, "") == build_cloudflare_command(18765)
    assert build_cloudflare_command(18765, "cf-jwt-token") == [
        "cloudflared",
        "tunnel",
        "--no-autoupdate",
        "run",
        "--token",
        "cf-jwt-token",
    ]


def test_build_bore_from_provider_config():
    assert build_bore_command(18765) == ["bore", "local", "18765", "--to", "bore.pub"]
    assert build_bore_command(18765, "my.relay.example") == [
        "bore",
        "local",
        "18765",
        "--to",
        "my.relay.example",
    ]
    assert build_bore_command(18765, "my.relay.example s3cret") == [
        "bore",
        "local",
        "18765",
        "--to",
        "my.relay.example",
        "--secret",
        "s3cret",
    ]
    assert build_bore_command(18765, "my.relay.example:s3cret") == [
        "bore",
        "local",
        "18765",
        "--to",
        "my.relay.example",
        "--secret",
        "s3cret",
    ]
    assert build_bore_command(18765, "onlysecret") == [
        "bore",
        "local",
        "18765",
        "--to",
        "bore.pub",
        "--secret",
        "onlysecret",
    ]


def test_parse_bore_provider_config():
    assert parse_bore_provider_config("") == ("bore.pub", "")
    assert parse_bore_provider_config("  ") == ("bore.pub", "")
    assert parse_bore_provider_config("host.example") == ("host.example", "")
    assert parse_bore_provider_config("host.example sec") == ("host.example", "sec")
    assert parse_bore_provider_config("localhost:sec") == ("localhost", "sec")
    # IPv6-looking values keep the whole string as server (no colon-split).
    assert parse_bore_provider_config("2001:db8::1") == ("2001:db8::1", "")
    assert parse_bore_provider_config("tok") == ("bore.pub", "tok")


def test_build_ngrok_and_tailscale():
    assert build_ngrok_command(18765) == [
        "ngrok",
        "http",
        "http://localhost:18765",
        "--log",
        "stdout",
        "--log-format",
        "json",
    ]
    assert build_ngrok_command(18765, "secret-token") == [
        "ngrok",
        "http",
        "http://localhost:18765",
        "--log",
        "stdout",
        "--log-format",
        "json",
        "--authtoken",
        "secret-token",
    ]
    assert build_tailscale_command(18765) == ["tailscale", "funnel", "18765"]


def test_parse_cloudflare_url():
    line = "2026-03-25T12:00:00Z INF |  https://abc-123.trycloudflare.com"
    assert parse_cloudflare_url(line) == "https://abc-123.trycloudflare.com"
    assert parse_cloudflare_url("INF Starting tunnel") is None
    # Token tunnels may log a custom hostname.
    assert parse_cloudflare_url("INF | https://mcp.example.com") == "https://mcp.example.com"


def test_parse_bore_url_adds_http_scheme():
    assert parse_bore_url("listening at bore.pub:45123") == "http://bore.pub:45123"
    assert parse_bore_url("waiting…") is None


def test_parse_ngrok_url_from_json():
    line = '{"msg":"started tunnel","url":"https://abc.ngrok-free.app"}'
    assert parse_ngrok_url(line) == "https://abc.ngrok-free.app"
    assert parse_ngrok_url('{"msg":"other"}') is None
    assert parse_ngrok_url("not json") is None


def test_parse_tailscale_url():
    line = "Available at https://node.tailnet-name.ts.net/"
    assert parse_tailscale_url(line) == "https://node.tailnet-name.ts.net"
    assert parse_tailscale_url("starting") is None


def test_normalize_public_base_and_mcp_url():
    assert normalize_public_base("bore.pub:1") == "http://bore.pub:1"
    assert normalize_public_base("https://x.trycloudflare.com/") == "https://x.trycloudflare.com"
    mgr = TunnelManager()
    mgr._public_url = "bore.pub:45123"
    assert mgr.mcp_public_url() == "http://bore.pub:45123/mcp"
    mgr._public_url = "https://abc-123.trycloudflare.com/"
    assert mgr.mcp_public_url() == "https://abc-123.trycloudflare.com/mcp"
    mgr._public_url = None
    assert mgr.mcp_public_url() is None


def test_provider_label():
    assert provider_label("cloudflare") == "Cloudflare"
    assert provider_label("ngrok") == "Ngrok"
    assert provider_label("unknown") == "Unknown"


def test_start_skips_when_testing_env(monkeypatch):
    monkeypatch.setenv("WRITERAGENT_TESTING", "1")
    mgr = TunnelManager()
    assert mgr.start(18765, "bore") is True
    assert mgr.is_running is False


def test_start_fails_unknown_provider(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    assert mgr.start(18765, "not-a-provider") is False


def test_start_fails_when_binary_missing(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    with patch("plugin.mcp.tunnel.binary_available", return_value=False):
        assert mgr.start(18765, "cloudflare") is False
    assert mgr.public_url is None


def test_start_parses_url_and_restarts_on_provider_change(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    started_cmds = []

    def _fake_async_process(cmd, stdout_cb=None, stderr_cb=None, on_exit_cb=None, **kwargs):
        proc = MagicMock()
        proc.is_running = True
        started_cmds.append(list(cmd))

        def start():
            if stderr_cb and cmd[0] == "cloudflared":
                stderr_cb("INF |  https://xyz.trycloudflare.com")
            elif stdout_cb and cmd[0] == "bore":
                stdout_cb("listening at bore.pub:9999")

        proc.start = start
        proc.terminate = MagicMock()
        return proc

    with (
        patch("plugin.mcp.tunnel.binary_available", return_value=True),
        patch("plugin.framework.worker_pool.AsyncProcess", side_effect=_fake_async_process),
    ):
        assert mgr.start(18765, "cloudflare") is True
        assert mgr.public_url == "https://xyz.trycloudflare.com"
        assert mgr.provider == "cloudflare"

        # Same port+provider → keep running (no second spawn).
        assert mgr.start(18765, "cloudflare") is True
        assert len(started_cmds) == 1

        # Provider change restarts.
        assert mgr.start(18765, "bore") is True
        assert len(started_cmds) == 2
        assert started_cmds[1][0] == "bore"
        assert mgr.public_url == "http://bore.pub:9999"
        assert mgr.provider == "bore"
        assert mgr.mcp_public_url() == "http://bore.pub:9999/mcp"
        mgr.stop()


def test_start_passes_provider_config_per_provider(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    started_cmds = []

    def _fake_async_process(cmd, stdout_cb=None, stderr_cb=None, on_exit_cb=None, **kwargs):
        proc = MagicMock()
        proc.is_running = True
        started_cmds.append(list(cmd))
        proc.start = MagicMock()
        proc.terminate = MagicMock()
        return proc

    with (
        patch("plugin.mcp.tunnel.binary_available", return_value=True),
        patch("plugin.framework.worker_pool.AsyncProcess", side_effect=_fake_async_process),
    ):
        assert mgr.start(18765, "ngrok", provider_token="tok-a") is True
        assert started_cmds[0][-2:] == ["--authtoken", "tok-a"]

        assert mgr.start(18765, "cloudflare", provider_token="cf-tok") is True
        assert started_cmds[1][-2:] == ["--token", "cf-tok"]

        assert mgr.start(18765, "bore", provider_token="relay.example sec") is True
        assert started_cmds[2] == [
            "bore",
            "local",
            "18765",
            "--to",
            "relay.example",
            "--secret",
            "sec",
        ]

        # Tailscale ignores Provider config.
        assert mgr.start(18765, "tailscale", provider_token="ignored") is True
        assert started_cmds[3] == ["tailscale", "funnel", "18765"]
        mgr.stop()


def test_redact_cmd_for_log_masks_secrets():
    assert "super-secret" not in _redact_cmd_for_log(build_ngrok_command(18765, "super-secret"))
    assert "--authtoken ***" in _redact_cmd_for_log(build_ngrok_command(18765, "super-secret"))
    assert "cf-jwt" not in _redact_cmd_for_log(build_cloudflare_command(1, "cf-jwt"))
    assert "--token ***" in _redact_cmd_for_log(build_cloudflare_command(1, "cf-jwt"))
    assert "s3cret" not in _redact_cmd_for_log(build_bore_command(1, "host.example s3cret"))
    assert "--secret ***" in _redact_cmd_for_log(build_bore_command(1, "host.example s3cret"))
    assert _redact_cmd_for_log(build_bore_command(1)) == "bore local 1 --to bore.pub"


def test_detect_tunnel_auth_error():
    assert detect_tunnel_auth_error("ngrok", '{"err":"ERR_NGROK_105"}') == (
        "ngrok authtoken required or invalid"
    )
    assert detect_tunnel_auth_error("cloudflare", "ERR invalid tunnel token") == (
        "cloudflare tunnel token invalid or unauthorized"
    )
    assert detect_tunnel_auth_error("bore", "listening at bore.pub:1") is None


def test_start_sets_last_error_when_binary_missing(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    with patch("plugin.mcp.tunnel.binary_available", return_value=False):
        assert mgr.start(18765, "cloudflare") is False
    assert mgr.last_error == "cloudflared binary not found on PATH"


def test_start_sets_last_error_unknown_provider(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    assert mgr.start(18765, "not-a-provider") is False
    assert mgr.last_error and "unknown" in mgr.last_error


def test_auth_line_and_exit_without_url_set_last_error(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    exit_cb = {"fn": None}

    def _fake_async_process(cmd, stdout_cb=None, stderr_cb=None, on_exit_cb=None, **kwargs):
        proc = MagicMock()
        proc.is_running = True
        exit_cb["fn"] = on_exit_cb

        def start():
            if stdout_cb:
                stdout_cb('{"err":"ERR_NGROK_105: authentication failed"}')

        proc.start = start
        proc.terminate = MagicMock()
        return proc

    with (
        patch("plugin.mcp.tunnel.binary_available", return_value=True),
        patch("plugin.framework.worker_pool.AsyncProcess", side_effect=_fake_async_process),
    ):
        assert mgr.start(18765, "ngrok") is True
        assert mgr.last_error == "ngrok authtoken required or invalid"
        assert mgr.public_url is None

        # Exit without URL keeps the auth error (does not overwrite).
        exit_cb["fn"](1)
        assert mgr.last_error == "ngrok authtoken required or invalid"
        assert mgr.is_running is False


def test_successful_url_clears_last_error_exit_without_prior_sets_code(monkeypatch):
    monkeypatch.delenv("WRITERAGENT_TESTING", raising=False)
    mgr = TunnelManager()
    exit_cb = {"fn": None}

    def _fake_async_process(cmd, stdout_cb=None, stderr_cb=None, on_exit_cb=None, **kwargs):
        proc = MagicMock()
        proc.is_running = True
        exit_cb["fn"] = on_exit_cb

        def start():
            if stderr_cb:
                stderr_cb("INF |  https://ok.trycloudflare.com")

        proc.start = start
        proc.terminate = MagicMock()
        return proc

    with (
        patch("plugin.mcp.tunnel.binary_available", return_value=True),
        patch("plugin.framework.worker_pool.AsyncProcess", side_effect=_fake_async_process),
    ):
        assert mgr.start(18765, "cloudflare") is True
        assert mgr.public_url == "https://ok.trycloudflare.com"
        assert mgr.last_error is None
        mgr.stop()
        assert mgr.last_error is None

    # Fresh start that exits before URL → generic exit message.
    # Call on_exit after start() returns — production fires it from a worker thread
    # (calling it inside start() while TunnelManager holds _lock would deadlock).
    def _fake_die(cmd, stdout_cb=None, stderr_cb=None, on_exit_cb=None, **kwargs):
        proc = MagicMock()
        proc.is_running = True
        exit_cb["fn"] = on_exit_cb
        proc.start = MagicMock()
        proc.terminate = MagicMock()
        return proc

    with (
        patch("plugin.mcp.tunnel.binary_available", return_value=True),
        patch("plugin.framework.worker_pool.AsyncProcess", side_effect=_fake_die),
    ):
        assert mgr.start(18765, "bore") is True
        exit_cb["fn"](2)
        assert mgr.last_error == "tunnel process exited (code 2)"
