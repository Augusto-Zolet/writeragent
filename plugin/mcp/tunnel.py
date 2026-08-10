# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
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
"""Lightweight public tunnel for MCP — hard-coded providers in one file.

Providers: cloudflare, bore, ngrok, tailscale. Settings expose enable, provider
select, and one shared ``mcp.tunnel_provider_token`` (“Provider config”) whose
meaning depends on the selected provider (ngrok authtoken, Cloudflare tunnel
token, Bore server / optional secret). Tailscale ignores it (CLI login).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from plugin.framework.worker_pool import AsyncProcess

log = logging.getLogger("writeragent.mcp.tunnel")

_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DEFAULT_PROVIDER = "cloudflare"
DEFAULT_BORE_SERVER = "bore.pub"

# ── Provider helpers (pure build/parse) ───────────────────────────────

_CLOUDFLARE_QUICK_URL_RE = re.compile(r"(https://[\w.-]+\.trycloudflare\.com)")
# Token / named tunnels may log a custom hostname (not trycloudflare.com).
_CLOUDFLARE_ANY_URL_RE = re.compile(r"(https://[\w.-]+)")
_BORE_URL_RE = re.compile(r"listening at ([\w.\-]+:\d+)")
_TAILSCALE_URL_RE = re.compile(r"Available at (https://[\w.\-]+/)")

_TAILSCALE_RESET_COMMANDS = (
    ["tailscale", "funnel", "reset"],
    ["tailscale", "serve", "reset"],
)

_REDACT_FLAGS = frozenset({"--authtoken", "--token", "--secret"})


def build_cloudflare_command(port: int, provider_token: str = "") -> list[str]:
    """Quick tunnel when config empty; ``run --token`` when Provider config set.

    Token tunnels use ingress configured in the Cloudflare dashboard (point that
    service at ``http://localhost:<mcp_port>``).
    """
    token = (provider_token or "").strip()
    if token:
        return [
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "run",
            "--token",
            token,
        ]
    return [
        "cloudflared",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://localhost:%s" % int(port),
    ]


def parse_cloudflare_url(line: str) -> Optional[str]:
    if not line:
        return None
    m = _CLOUDFLARE_QUICK_URL_RE.search(line)
    if m:
        return m.group(1)
    m = _CLOUDFLARE_ANY_URL_RE.search(line)
    return m.group(1) if m else None


def parse_bore_provider_config(value: str) -> tuple[str, str]:
    """Parse Provider config for Bore → ``(server, secret)``.

    - empty → (bore.pub, "")
    - ``host secret`` (whitespace) → server + secret
    - ``host:secret`` when host looks like a hostname (has ``.`` or localhost),
      and the value is not IPv6 (multiple ``:``)
    - value with no ``.`` (and not localhost) → secret for default bore.pub
    - otherwise → server only
    """
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_BORE_SERVER, ""

    if any(ch.isspace() for ch in raw):
        parts = raw.split()
        server = parts[0]
        secret = " ".join(parts[1:]).strip()
        return server or DEFAULT_BORE_SERVER, secret

    colon_count = raw.count(":")
    if colon_count == 1:
        host, secret = raw.split(":", 1)
        host = host.strip()
        secret = secret.strip()
        if host and secret and (host == "localhost" or "." in host):
            return host, secret
    elif colon_count > 1:
        # IPv6 (or similar) — keep whole string as server; use "host secret" for secrets.
        return raw, ""

    if raw.lower() != "localhost" and "." not in raw:
        return DEFAULT_BORE_SERVER, raw

    return raw, ""


def build_bore_command(port: int, provider_token: str = "") -> list[str]:
    server, secret = parse_bore_provider_config(provider_token)
    cmd = ["bore", "local", str(int(port)), "--to", server]
    if secret:
        cmd.extend(["--secret", secret])
    return cmd


def parse_bore_url(line: str) -> Optional[str]:
    if not line:
        return None
    m = _BORE_URL_RE.search(line)
    if not m:
        return None
    # bore prints host:port with no scheme — normalize for mcp_public_url.
    return "http://%s" % m.group(1)


def build_ngrok_command(port: int, authtoken: str = "") -> list[str]:
    # Empty token → rely on ngrok CLI config / env (prior behavior).
    cmd = [
        "ngrok",
        "http",
        "http://localhost:%s" % int(port),
        "--log",
        "stdout",
        "--log-format",
        "json",
    ]
    token = (authtoken or "").strip()
    if token:
        cmd.extend(["--authtoken", token])
    return cmd


def parse_ngrok_url(line: str) -> Optional[str]:
    if not line or not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
    except Exception:
        return None
    if data.get("msg") == "started tunnel" and data.get("url"):
        return str(data["url"])
    return None


def detect_tunnel_auth_error(provider: str, line: str) -> Optional[str]:
    """Return a short user-facing reason when a tunnel CLI line looks like auth failure."""
    if not line:
        return None
    lower = line.lower()
    provider = (provider or "").strip().lower()

    if provider == "ngrok":
        if "ERR_NGROK_105" in line or (
            "authtoken" in lower
            and ("required" in lower or "invalid" in lower or "unauthorized" in lower)
        ):
            return "ngrok authtoken required or invalid"
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except Exception:
                data = None
            if isinstance(data, dict):
                err = str(data.get("err") or data.get("error") or "")
                if "ERR_NGROK_105" in err or "authtoken" in err.lower():
                    return "ngrok authtoken required or invalid"

    if provider == "cloudflare":
        if any(
            phrase in lower
            for phrase in (
                "unauthorized",
                "invalid token",
                "invalid tunnel token",
                "failed to parse tunnel token",
                "bad tunnel token",
            )
        ):
            return "cloudflare tunnel token invalid or unauthorized"

    if provider == "bore" and ("unauthorized" in lower or "invalid secret" in lower):
        return "bore secret rejected by server"

    return None


def build_tailscale_command(port: int) -> list[str]:
    return ["tailscale", "funnel", str(int(port))]


def parse_tailscale_url(line: str) -> Optional[str]:
    if not line:
        return None
    m = _TAILSCALE_URL_RE.search(line)
    if not m:
        return None
    return m.group(1).rstrip("/")


def _tailscale_reset() -> None:
    for cmd in _TAILSCALE_RESET_COMMANDS:
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_CREATION_FLAGS,
            )
            log.debug("Tailscale reset: %s", " ".join(cmd))
        except Exception:
            log.debug("Tailscale reset failed: %s", " ".join(cmd), exc_info=True)


# label used in status toasts; version_args / install_url for binary check.
PROVIDERS: dict[str, dict] = {
    "cloudflare": {
        "label": "Cloudflare",
        "version_args": ["cloudflared", "--version"],
        "install_url": (
            "https://developers.cloudflare.com/cloudflare-one/connections/"
            "connect-networks/downloads/"
        ),
        "build_command": build_cloudflare_command,
        "parse_line": parse_cloudflare_url,
        "pre_start": None,
        "post_stop": None,
    },
    "bore": {
        "label": "Bore",
        "version_args": ["bore", "--version"],
        "install_url": "https://github.com/ekzhang/bore/releases",
        "build_command": build_bore_command,
        "parse_line": parse_bore_url,
        "pre_start": None,
        "post_stop": None,
    },
    "ngrok": {
        "label": "Ngrok",
        "version_args": ["ngrok", "version"],
        "install_url": "https://ngrok.com/download",
        "build_command": build_ngrok_command,
        "parse_line": parse_ngrok_url,
        "pre_start": None,
        "post_stop": None,
    },
    "tailscale": {
        "label": "Tailscale",
        "version_args": ["tailscale", "version"],
        "install_url": "https://tailscale.com/download",
        "build_command": build_tailscale_command,
        "parse_line": parse_tailscale_url,
        "pre_start": _tailscale_reset,
        "post_stop": _tailscale_reset,
    },
}


def provider_label(name: str) -> str:
    info = PROVIDERS.get(name)
    if info:
        return str(info["label"])
    return name.title() if name else DEFAULT_PROVIDER.title()


def binary_available(provider: str) -> bool:
    """True when the provider binary can be executed."""
    info = PROVIDERS.get(provider)
    if not info:
        log.error("Unknown tunnel provider: %s", provider)
        return False
    version_args = info["version_args"]
    install_url = info["install_url"]
    try:
        result = subprocess.run(
            version_args,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATION_FLAGS,
        )
        ver = (result.stdout or result.stderr or "").strip()
        log.info("%s version: %s", provider, ver or "(empty)")
        return True
    except FileNotFoundError:
        log.error(
            "%s binary not found on PATH. Install from: %s",
            version_args[0],
            install_url,
        )
        return False
    except Exception:
        log.exception("Error checking %s binary", provider)
        return False


def normalize_public_base(url: str) -> str:
    """Ensure a tunnel base URL has a scheme (bore prints host:port)."""
    base = url.rstrip("/")
    if "://" not in base:
        return "http://%s" % base
    return base


def _build_provider_command(provider: str, port: int, provider_token: str) -> list[str]:
    """Dispatch Provider config into the selected provider's CLI argv."""
    if provider == "ngrok":
        return build_ngrok_command(port, provider_token)
    if provider == "cloudflare":
        return build_cloudflare_command(port, provider_token)
    if provider == "bore":
        return build_bore_command(port, provider_token)
    info = PROVIDERS[provider]
    return info["build_command"](port)


class TunnelManager:
    """Owns a single tunnel subprocess for the selected provider."""

    def __init__(self) -> None:
        self._process: Optional[AsyncProcess] = None
        self._public_url: Optional[str] = None
        self._lock = threading.Lock()
        self._port: Optional[int] = None
        self._provider: Optional[str] = None
        self._provider_token: str = ""
        self._last_error: Optional[str] = None

    @property
    def public_url(self) -> Optional[str]:
        return self._public_url

    @property
    def provider(self) -> Optional[str]:
        return self._provider

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_running

    @property
    def last_error(self) -> Optional[str]:
        """Short reason for the last failed start / auth / early exit, if any."""
        return self._last_error

    def mcp_public_url(self) -> Optional[str]:
        """Streamable-HTTP MCP endpoint on the public tunnel, if known."""
        base = self._public_url
        if not base:
            return None
        return "%s/mcp" % normalize_public_base(base)

    def start(
        self,
        port: int,
        provider: str = DEFAULT_PROVIDER,
        provider_token: str = "",
    ) -> bool:
        """Start (or keep) a tunnel to *port*. Returns False if start failed."""
        import os

        if os.environ.get("WRITERAGENT_TESTING"):
            return True

        provider = (provider or DEFAULT_PROVIDER).strip().lower()
        token = (provider_token or "").strip()
        info = PROVIDERS.get(provider)
        if info is None:
            log.error("Unknown tunnel provider: %s", provider)
            self._last_error = "unknown tunnel provider: %s" % provider
            return False

        with self._lock:
            if (
                self.is_running
                and self._port == int(port)
                and self._provider == provider
                and self._provider_token == token
            ):
                log.info("Tunnel already running (%s) at %s", provider, self._public_url)
                if self._public_url:
                    self._last_error = None
                return True
            if self.is_running:
                self._stop_unlocked()

            if not binary_available(provider):
                binary = info["version_args"][0]
                self._last_error = "%s binary not found on PATH" % binary
                return False

            pre_start: Optional[Callable[[], None]] = info.get("pre_start")
            if pre_start:
                try:
                    pre_start()
                except Exception:
                    log.exception("Tunnel pre_start failed for %s", provider)
                    self._last_error = "%s pre_start failed" % provider
                    return False

            parse_line: Callable[[str], Optional[str]] = info["parse_line"]
            cmd = _build_provider_command(provider, int(port), token)
            log.info("Starting MCP tunnel (%s): %s", provider, _redact_cmd_for_log(cmd))
            self._public_url = None
            self._port = int(port)
            self._provider = provider
            self._provider_token = token
            self._last_error = None

            def _on_line(line: str) -> None:
                if self._public_url:
                    return
                auth_err = detect_tunnel_auth_error(provider, line)
                if auth_err:
                    self._last_error = auth_err
                    log.error("MCP tunnel auth error (%s): %s", provider, auth_err)
                url = parse_line(line)
                if url:
                    self._public_url = url
                    self._last_error = None
                    log.info("MCP tunnel URL (%s): %s", provider, url)

            def _on_exit(rc: int) -> None:
                log.info("MCP tunnel process (%s) exited with code %s", provider, rc)
                with self._lock:
                    had_url = self._public_url is not None
                    self._process = None
                    self._public_url = None
                    self._port = None
                    self._provider = None
                    self._provider_token = ""
                    if had_url:
                        self._last_error = None
                    elif not self._last_error:
                        self._last_error = "tunnel process exited (code %s)" % rc

            try:
                from plugin.framework.worker_pool import AsyncProcess

                # Some CLIs (cloudflared) print the URL on stderr more often than stdout.
                self._process = AsyncProcess(
                    cmd,
                    stdout_cb=_on_line,
                    stderr_cb=_on_line,
                    on_exit_cb=_on_exit,
                    creationflags=_CREATION_FLAGS,
                )
                self._process.start()
                return True
            except FileNotFoundError:
                log.error("%s binary not found", info["version_args"][0])
                self._process = None
                self._port = None
                self._provider = None
                self._provider_token = ""
                self._last_error = "%s binary not found on PATH" % info["version_args"][0]
                return False
            except Exception:
                log.exception("Failed to start MCP tunnel (%s)", provider)
                self._process = None
                self._port = None
                self._provider = None
                self._provider_token = ""
                self._last_error = "failed to start %s tunnel" % provider
                return False

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        provider = self._provider
        proc = self._process
        if proc is None:
            self._public_url = None
            self._port = None
            self._provider = None
            self._provider_token = ""
            self._last_error = None
            return
        try:
            proc.terminate()
        except Exception:
            log.exception("Error stopping MCP tunnel")
        finally:
            self._process = None
            self._public_url = None
            self._port = None
            self._provider = None
            self._provider_token = ""
            self._last_error = None
            info = PROVIDERS.get(provider or "")
            post_stop = info.get("post_stop") if info else None
            if post_stop:
                try:
                    post_stop()
                except Exception:
                    log.exception("Tunnel post_stop failed for %s", provider)


def _redact_cmd_for_log(cmd: list[str]) -> str:
    """Join argv for logs; mask values after secret-bearing flags."""
    out: list[str] = []
    skip_next = False
    for part in cmd:
        if skip_next:
            out.append("***")
            skip_next = False
            continue
        if part in _REDACT_FLAGS:
            out.append(part)
            skip_next = True
            continue
        out.append(part)
    return " ".join(out)
