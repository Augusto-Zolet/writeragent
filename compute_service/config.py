# WriterAgent - Python Compute Service Configuration
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone settings for the Python compute service.

No UNO / writeragent.json dependency. Layered sources (later wins):

1. Secure defaults
2. Optional ``--config`` / ``PYTHON_COMPUTE_CONFIG`` JSON file
3. ``PYTHON_COMPUTE_*`` environment
4. Explicit CLI overrides (``--host``, ``--port``, ``--api-key-file``)

Secrets come from ``PYTHON_COMPUTE_API_KEY`` or a key file — never from argv.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
_DEFAULT_MAX_BODY_BYTES = 32 * 1024 * 1024
_DEFAULT_TIMEOUT_SEC = 30
_MAX_TIMEOUT_SEC = 600
_DEFAULT_THREADS = 2
_DEFAULT_WORKERS = 1
_DEFAULT_WORKER_MAX_TASKS = 500
_DEFAULT_SHARED_KERNEL_TTL_SEC = 3600.0
_DEFAULT_IDLE_WORKER_TTL_SEC = 3600.0
_DEFAULT_OCR_WORKERS = 0
_DEFAULT_OCR_TIMEOUT_SEC = 60
_DEFAULT_OCR_MAX_TASKS = 100
_DEFAULT_MAX_CODE_CHARS = 262144
_DEFAULT_MAX_INFLIGHT_PER_SESSION = 2
_MIN_MAX_CODE_CHARS = 64

_DEFAULT_LOG_LEVEL = "INFO"
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL"})

_LOOPBACK_HOSTS = frozenset({"", "127.0.0.1", "::1", "localhost"})


def normalize_log_level(level: str) -> str:
    """Normalize log level strings (e.g. WARN -> WARNING)."""
    norm = (level or "").strip().upper()
    return "WARNING" if norm == "WARN" else norm


class ConfigError(ValueError):
    """Invalid compute-service configuration."""


def ocr_path_is_allowed(file_path: str, allow_prefixes: tuple[str, ...] | list[str]) -> bool:
    """True if *file_path* resolves to a file under one allowlisted prefix.

    Empty *allow_prefixes* denies every path (callers should use image_b64).
    """
    prefixes = [str(p).strip() for p in allow_prefixes if str(p).strip()]
    if not prefixes:
        return False
    try:
        resolved = os.path.realpath(os.path.expanduser(file_path.strip()))
    except (OSError, ValueError, TypeError):
        return False
    if not os.path.isfile(resolved):
        # Allowlist check still applies for missing files so we do not leak existence
        # via a different error before prefix match. Prefix-only:
        pass
    for raw in prefixes:
        try:
            base = os.path.realpath(os.path.expanduser(raw))
        except (OSError, ValueError):
            continue
        if resolved == base or resolved.startswith(base + os.sep):
            return True
    return False


@dataclass(frozen=True)
class ComputeSettings:
    """Immutable process settings for one compute-service instance."""

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    api_key: str = ""
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES
    default_timeout_sec: int = _DEFAULT_TIMEOUT_SEC
    max_timeout_sec: int = _MAX_TIMEOUT_SEC
    threads: int = _DEFAULT_THREADS
    workers: int = _DEFAULT_WORKERS
    worker_max_tasks: int = _DEFAULT_WORKER_MAX_TASKS
    shared_kernel_ttl_sec: float = _DEFAULT_SHARED_KERNEL_TTL_SEC
    idle_worker_ttl_sec: float = _DEFAULT_IDLE_WORKER_TTL_SEC
    ocr_workers: int = _DEFAULT_OCR_WORKERS
    ocr_timeout_sec: int = _DEFAULT_OCR_TIMEOUT_SEC
    ocr_max_tasks: int = _DEFAULT_OCR_MAX_TASKS
    max_code_chars: int = _DEFAULT_MAX_CODE_CHARS
    max_inflight: int = 0  # 0 → computed in __init__ as max(threads, workers) * 2
    max_inflight_per_session: int = _DEFAULT_MAX_INFLIGHT_PER_SESSION
    ocr_allow_paths: tuple[str, ...] = ()
    log_level: str = _DEFAULT_LOG_LEVEL
    # Future: map authenticated principals to named profiles. Today always "default".
    default_principal: str = "default"

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        api_key: str = "",
        max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
        default_timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
        max_timeout_sec: int = _MAX_TIMEOUT_SEC,
        threads: int | None = None,
        max_threads: int | None = None,
        workers: int | None = None,
        max_workers: int | None = None,
        worker_max_tasks: int = _DEFAULT_WORKER_MAX_TASKS,
        shared_kernel_ttl_sec: float = _DEFAULT_SHARED_KERNEL_TTL_SEC,
        idle_worker_ttl_sec: float = _DEFAULT_IDLE_WORKER_TTL_SEC,
        ocr_workers: int = _DEFAULT_OCR_WORKERS,
        ocr_timeout_sec: int = _DEFAULT_OCR_TIMEOUT_SEC,
        ocr_max_tasks: int = _DEFAULT_OCR_MAX_TASKS,
        max_code_chars: int = _DEFAULT_MAX_CODE_CHARS,
        max_inflight: int | None = None,
        max_inflight_per_session: int = _DEFAULT_MAX_INFLIGHT_PER_SESSION,
        ocr_allow_paths: tuple[str, ...] | list[str] = (),
        log_level: str = _DEFAULT_LOG_LEVEL,
        default_principal: str = "default",
    ) -> None:
        eff_threads = _DEFAULT_THREADS if threads is None and max_threads is None else (threads if max_threads is None else max_threads)
        eff_workers = _DEFAULT_WORKERS if workers is None and max_workers is None else (workers if max_workers is None else max_workers)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "max_body_bytes", max_body_bytes)
        object.__setattr__(self, "default_timeout_sec", default_timeout_sec)
        object.__setattr__(self, "max_timeout_sec", max_timeout_sec)
        object.__setattr__(self, "threads", eff_threads)
        object.__setattr__(self, "workers", eff_workers)
        object.__setattr__(self, "worker_max_tasks", worker_max_tasks)
        object.__setattr__(self, "shared_kernel_ttl_sec", float(shared_kernel_ttl_sec))
        object.__setattr__(self, "idle_worker_ttl_sec", float(idle_worker_ttl_sec))
        object.__setattr__(self, "ocr_workers", ocr_workers)
        object.__setattr__(self, "ocr_timeout_sec", ocr_timeout_sec)
        object.__setattr__(self, "ocr_max_tasks", ocr_max_tasks)
        object.__setattr__(self, "max_code_chars", int(max_code_chars))
        thread_n = _DEFAULT_THREADS if eff_threads is None else int(eff_threads)
        worker_n = _DEFAULT_WORKERS if eff_workers is None else int(eff_workers)
        computed_inflight = max(thread_n, worker_n) * 2
        object.__setattr__(self, "max_inflight", computed_inflight if max_inflight is None else int(max_inflight))
        object.__setattr__(self, "max_inflight_per_session", int(max_inflight_per_session))
        object.__setattr__(self, "ocr_allow_paths", tuple(str(p) for p in ocr_allow_paths if str(p).strip()))
        object.__setattr__(self, "log_level", log_level)
        object.__setattr__(self, "default_principal", default_principal)

    @property
    def max_threads(self) -> int:
        """Alias for threads (HTTP listener capacity)."""
        return self.threads

    @property
    def max_workers(self) -> int:
        """Alias for workers (formula subprocess pool)."""
        return self.workers

    @property
    def auth_required(self) -> bool:
        return bool(self.api_key)

    @property
    def is_loopback_bind(self) -> bool:
        return self.host in _LOOPBACK_HOSTS

    def validate(self) -> None:
        if not (1 <= self.port <= 65535):
            raise ConfigError(f"Invalid port: {self.port}")
        if self.max_body_bytes < 1024:
            raise ConfigError("max_body_bytes must be at least 1024")
        if self.default_timeout_sec < 1 or self.max_timeout_sec < 1:
            raise ConfigError("timeout bounds must be >= 1")
        if self.default_timeout_sec > self.max_timeout_sec:
            raise ConfigError("default_timeout_sec cannot exceed max_timeout_sec")
        if self.threads < 1:
            raise ConfigError("threads must be >= 1")
        if self.workers < 1:
            raise ConfigError("workers must be >= 1")
        if self.worker_max_tasks < 1:
            raise ConfigError("worker_max_tasks must be >= 1")
        if self.ocr_workers < 0:
            raise ConfigError("ocr_workers must be >= 0")
        if self.ocr_timeout_sec < 1:
            raise ConfigError("ocr_timeout_sec must be >= 1")
        if self.ocr_max_tasks < 1:
            raise ConfigError("ocr_max_tasks must be >= 1")
        if self.max_code_chars < _MIN_MAX_CODE_CHARS:
            raise ConfigError(f"max_code_chars must be >= {_MIN_MAX_CODE_CHARS}")
        if self.max_inflight < 1:
            raise ConfigError("max_inflight must be >= 1")
        if self.max_inflight_per_session < 1:
            raise ConfigError("max_inflight_per_session must be >= 1")
        if self.shared_kernel_ttl_sec < 0:
            raise ConfigError("shared_kernel_ttl_sec must be >= 0")
        if self.idle_worker_ttl_sec < 0:
            raise ConfigError("idle_worker_ttl_sec must be >= 0")
        if self.log_level.upper() not in _VALID_LOG_LEVELS:
            raise ConfigError(f"Invalid log_level: {self.log_level!r} (must be one of {sorted(_VALID_LOG_LEVELS)})")
        # No API key ⇒ no auth (dev/test). Verification runs only when a key is set.


def _as_path_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(os.pathsep) if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    raise ConfigError(f"ocr_allow_paths must be a list or {os.pathsep}-separated string")


def _as_int(value: Any, *, field: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid integer for {field}: {value!r}") from exc


def _read_key_file(path: str | Path) -> str:
    key_path = Path(path).expanduser()
    try:
        text = key_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read api_key_file {key_path}: {exc}") from exc
    # Strip one trailing newline only if present; keep interior whitespace.
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n") or text.endswith("\r"):
        text = text[:-1]
    # Do NOT call text.strip() — that would silently mangle keys with leading/trailing spaces.
    if not text:
        raise ConfigError(f"api_key_file {key_path} is empty")
    return text


def _load_json_file(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path).expanduser()
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {cfg_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file {cfg_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {cfg_path} must contain a JSON object")
    return raw


def _flatten_config_json(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Accept flat keys or nested ``listen`` / ``auth`` / ``limits`` / ``ocr`` sections."""
    out: dict[str, Any] = {}
    listen = raw.get("listen")
    if isinstance(listen, Mapping):
        if "host" in listen:
            out["host"] = listen["host"]
        if "port" in listen:
            out["port"] = listen["port"]
    auth = raw.get("auth")
    if isinstance(auth, Mapping):
        if "api_key_file" in auth:
            out["api_key_file"] = auth["api_key_file"]
        # Deliberately ignore raw "api_key" in JSON files — prefer env / key file.
    limits = raw.get("limits")
    if isinstance(limits, Mapping):
        if "max_body_bytes" in limits:
            out["max_body_bytes"] = limits["max_body_bytes"]
        if "default_timeout_sec" in limits:
            out["default_timeout_sec"] = limits["default_timeout_sec"]
        if "max_timeout_sec" in limits:
            out["max_timeout_sec"] = limits["max_timeout_sec"]
        if "threads" in limits:
            out["threads"] = limits["threads"]
        elif "max_threads" in limits:
            out["threads"] = limits["max_threads"]
        if "workers" in limits:
            out["workers"] = limits["workers"]
        elif "max_workers" in limits:
            out["workers"] = limits["max_workers"]
        if "worker_max_tasks" in limits:
            out["worker_max_tasks"] = limits["worker_max_tasks"]
        if "shared_kernel_ttl_sec" in limits:
            out["shared_kernel_ttl_sec"] = limits["shared_kernel_ttl_sec"]
        elif "session_ttl_sec" in limits:
            out["shared_kernel_ttl_sec"] = limits["session_ttl_sec"]
        if "idle_worker_ttl_sec" in limits:
            out["idle_worker_ttl_sec"] = limits["idle_worker_ttl_sec"]
        if "max_code_chars" in limits:
            out["max_code_chars"] = limits["max_code_chars"]
        if "max_inflight" in limits:
            out["max_inflight"] = limits["max_inflight"]
        if "max_inflight_per_session" in limits:
            out["max_inflight_per_session"] = limits["max_inflight_per_session"]
    ocr_cfg = raw.get("ocr")
    if isinstance(ocr_cfg, Mapping):
        if "workers" in ocr_cfg:
            out["ocr_workers"] = ocr_cfg["workers"]
        if "timeout_sec" in ocr_cfg:
            out["ocr_timeout_sec"] = ocr_cfg["timeout_sec"]
        if "max_tasks" in ocr_cfg:
            out["ocr_max_tasks"] = ocr_cfg["max_tasks"]
        if "allow_paths" in ocr_cfg:
            out["ocr_allow_paths"] = ocr_cfg["allow_paths"]
    logging_cfg = raw.get("logging")
    if isinstance(logging_cfg, Mapping):
        if "log_level" in logging_cfg:
            out["log_level"] = logging_cfg["log_level"]
        elif "level" in logging_cfg:
            out["log_level"] = logging_cfg["level"]

    for key in (
        "host",
        "port",
        "api_key_file",
        "max_body_bytes",
        "default_timeout_sec",
        "max_timeout_sec",
        "threads",
        "max_threads",
        "workers",
        "max_workers",
        "worker_max_tasks",
        "shared_kernel_ttl_sec",
        "session_ttl_sec",
        "idle_worker_ttl_sec",
        "ocr_workers",
        "ocr_timeout_sec",
        "ocr_max_tasks",
        "ocr_allow_paths",
        "max_code_chars",
        "max_inflight",
        "max_inflight_per_session",
        "log_level",
    ):
        if key in raw and key not in out:
            out[key] = raw[key]
    if "session_ttl_sec" in out and "shared_kernel_ttl_sec" not in out:
        out["shared_kernel_ttl_sec"] = out.pop("session_ttl_sec")
    if "max_threads" in out and "threads" not in out:
        out["threads"] = out["max_threads"]
    if "max_workers" in out and "workers" not in out:
        out["workers"] = out["max_workers"]
    return out


def load_settings(
    *,
    config_path: str | Path | None = None,
    host: str | None = None,
    port: int | None = None,
    threads: int | None = None,
    max_threads: int | None = None,
    workers: int | None = None,
    max_workers: int | None = None,
    worker_max_tasks: int | None = None,
    ocr_workers: int | None = None,
    ocr_timeout_sec: int | None = None,
    ocr_max_tasks: int | None = None,
    api_key_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ComputeSettings:
    """Resolve settings from defaults → JSON → env → explicit CLI overrides."""
    env = os.environ if environ is None else environ

    values: dict[str, Any] = {
        "host": _DEFAULT_HOST,
        "port": _DEFAULT_PORT,
        "api_key": "",
        "max_body_bytes": _DEFAULT_MAX_BODY_BYTES,
        "default_timeout_sec": _DEFAULT_TIMEOUT_SEC,
        "max_timeout_sec": _MAX_TIMEOUT_SEC,
        "threads": _DEFAULT_THREADS,
        "workers": _DEFAULT_WORKERS,
        "worker_max_tasks": _DEFAULT_WORKER_MAX_TASKS,
        "shared_kernel_ttl_sec": _DEFAULT_SHARED_KERNEL_TTL_SEC,
        "idle_worker_ttl_sec": _DEFAULT_IDLE_WORKER_TTL_SEC,
        "ocr_workers": _DEFAULT_OCR_WORKERS,
        "ocr_timeout_sec": _DEFAULT_OCR_TIMEOUT_SEC,
        "ocr_max_tasks": _DEFAULT_OCR_MAX_TASKS,
        "max_code_chars": _DEFAULT_MAX_CODE_CHARS,
        "max_inflight": None,
        "max_inflight_per_session": _DEFAULT_MAX_INFLIGHT_PER_SESSION,
        "ocr_allow_paths": (),
        "log_level": _DEFAULT_LOG_LEVEL,
    }

    resolved_config = config_path or env.get("PYTHON_COMPUTE_CONFIG") or ""
    if resolved_config:
        values.update(_flatten_config_json(_load_json_file(resolved_config)))

    # Environment settings.
    if env.get("PYTHON_COMPUTE_HOST"):
        values["host"] = env["PYTHON_COMPUTE_HOST"]

    if env.get("PYTHON_COMPUTE_PORT"):
        values["port"] = env["PYTHON_COMPUTE_PORT"]

    if env.get("PYTHON_COMPUTE_MAX_BODY_BYTES"):
        values["max_body_bytes"] = env["PYTHON_COMPUTE_MAX_BODY_BYTES"]
    if env.get("PYTHON_COMPUTE_DEFAULT_TIMEOUT_SEC"):
        values["default_timeout_sec"] = env["PYTHON_COMPUTE_DEFAULT_TIMEOUT_SEC"]
    if env.get("PYTHON_COMPUTE_MAX_TIMEOUT_SEC"):
        values["max_timeout_sec"] = env["PYTHON_COMPUTE_MAX_TIMEOUT_SEC"]
    if env.get("PYTHON_COMPUTE_THREADS"):
        values["threads"] = env["PYTHON_COMPUTE_THREADS"]
    elif env.get("PYTHON_COMPUTE_MAX_THREADS"):
        values["threads"] = env["PYTHON_COMPUTE_MAX_THREADS"]

    if env.get("PYTHON_COMPUTE_WORKERS"):
        values["workers"] = env["PYTHON_COMPUTE_WORKERS"]
    elif env.get("PYTHON_COMPUTE_MAX_WORKERS"):
        values["workers"] = env["PYTHON_COMPUTE_MAX_WORKERS"]

    if env.get("PYTHON_COMPUTE_WORKER_MAX_TASKS"):
        values["worker_max_tasks"] = env["PYTHON_COMPUTE_WORKER_MAX_TASKS"]
    if env.get("PYTHON_COMPUTE_SHARED_KERNEL_TTL_SEC"):
        values["shared_kernel_ttl_sec"] = env["PYTHON_COMPUTE_SHARED_KERNEL_TTL_SEC"]
    elif env.get("PYTHON_COMPUTE_SESSION_TTL_SEC"):
        values["shared_kernel_ttl_sec"] = env["PYTHON_COMPUTE_SESSION_TTL_SEC"]
    if env.get("PYTHON_COMPUTE_IDLE_WORKER_TTL_SEC"):
        values["idle_worker_ttl_sec"] = env["PYTHON_COMPUTE_IDLE_WORKER_TTL_SEC"]
    if env.get("PYTHON_COMPUTE_OCR_WORKERS"):
        values["ocr_workers"] = env["PYTHON_COMPUTE_OCR_WORKERS"]
    if env.get("PYTHON_COMPUTE_OCR_TIMEOUT_SEC"):
        values["ocr_timeout_sec"] = env["PYTHON_COMPUTE_OCR_TIMEOUT_SEC"]
    if env.get("PYTHON_COMPUTE_OCR_MAX_TASKS"):
        values["ocr_max_tasks"] = env["PYTHON_COMPUTE_OCR_MAX_TASKS"]
    if env.get("PYTHON_COMPUTE_MAX_CODE_CHARS"):
        values["max_code_chars"] = env["PYTHON_COMPUTE_MAX_CODE_CHARS"]
    if env.get("PYTHON_COMPUTE_MAX_INFLIGHT"):
        values["max_inflight"] = env["PYTHON_COMPUTE_MAX_INFLIGHT"]
    if env.get("PYTHON_COMPUTE_MAX_INFLIGHT_PER_SESSION"):
        values["max_inflight_per_session"] = env["PYTHON_COMPUTE_MAX_INFLIGHT_PER_SESSION"]
    if env.get("PYTHON_COMPUTE_OCR_ALLOW_PATHS"):
        values["ocr_allow_paths"] = env["PYTHON_COMPUTE_OCR_ALLOW_PATHS"]
    if env.get("PYTHON_COMPUTE_LOG_LEVEL"):
        values["log_level"] = env["PYTHON_COMPUTE_LOG_LEVEL"]

    env_key = (env.get("PYTHON_COMPUTE_API_KEY") or "").strip()
    env_key_file = (env.get("PYTHON_COMPUTE_API_KEY_FILE") or "").strip()
    json_key_file = str(values.pop("api_key_file", "") or "").strip()

    # Explicit CLI overrides last.
    if host is not None:
        values["host"] = host
    if port is not None:
        values["port"] = port
    if threads is not None:
        values["threads"] = threads
    elif max_threads is not None:
        values["threads"] = max_threads

    if workers is not None:
        values["workers"] = workers
    elif max_workers is not None:
        values["workers"] = max_workers

    if worker_max_tasks is not None:
        values["worker_max_tasks"] = worker_max_tasks
    if ocr_workers is not None:
        values["ocr_workers"] = ocr_workers
    if ocr_timeout_sec is not None:
        values["ocr_timeout_sec"] = ocr_timeout_sec
    if ocr_max_tasks is not None:
        values["ocr_max_tasks"] = ocr_max_tasks

    # Secret resolution: CLI key-file > env key > env key-file > JSON key-file.
    api_key = ""
    chosen_key_file = api_key_file or env_key_file or json_key_file or None
    if api_key_file:
        api_key = _read_key_file(api_key_file)
    elif env_key:
        api_key = env_key
    elif chosen_key_file:
        api_key = _read_key_file(chosen_key_file)

    def _as_float(val: Any, field: str, default: float) -> float:
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{field} must be a number: {val}") from exc

    settings = ComputeSettings(
        host=str(values["host"] or _DEFAULT_HOST),
        port=_as_int(values["port"], field="port", default=_DEFAULT_PORT),
        api_key=api_key,
        max_body_bytes=_as_int(
            values["max_body_bytes"], field="max_body_bytes", default=_DEFAULT_MAX_BODY_BYTES
        ),
        default_timeout_sec=_as_int(
            values["default_timeout_sec"],
            field="default_timeout_sec",
            default=_DEFAULT_TIMEOUT_SEC,
        ),
        max_timeout_sec=_as_int(
            values["max_timeout_sec"], field="max_timeout_sec", default=_MAX_TIMEOUT_SEC
        ),
        threads=_as_int(
            values["threads"], field="threads", default=_DEFAULT_THREADS
        ),
        workers=_as_int(
            values["workers"], field="workers", default=_DEFAULT_WORKERS
        ),
        worker_max_tasks=_as_int(
            values["worker_max_tasks"], field="worker_max_tasks", default=_DEFAULT_WORKER_MAX_TASKS
        ),
        shared_kernel_ttl_sec=_as_float(
            values.get("shared_kernel_ttl_sec"), field="shared_kernel_ttl_sec", default=_DEFAULT_SHARED_KERNEL_TTL_SEC
        ),
        idle_worker_ttl_sec=_as_float(
            values.get("idle_worker_ttl_sec"), field="idle_worker_ttl_sec", default=_DEFAULT_IDLE_WORKER_TTL_SEC
        ),
        ocr_workers=_as_int(
            values["ocr_workers"], field="ocr_workers", default=_DEFAULT_OCR_WORKERS
        ),
        ocr_timeout_sec=_as_int(
            values["ocr_timeout_sec"], field="ocr_timeout_sec", default=_DEFAULT_OCR_TIMEOUT_SEC
        ),
        ocr_max_tasks=_as_int(
            values["ocr_max_tasks"], field="ocr_max_tasks", default=_DEFAULT_OCR_MAX_TASKS
        ),
        max_code_chars=_as_int(
            values.get("max_code_chars"), field="max_code_chars", default=_DEFAULT_MAX_CODE_CHARS
        ),
        max_inflight=(
            None
            if values.get("max_inflight") is None or values.get("max_inflight") == ""
            else _as_int(values.get("max_inflight"), field="max_inflight", default=1)
        ),
        max_inflight_per_session=_as_int(
            values.get("max_inflight_per_session"),
            field="max_inflight_per_session",
            default=_DEFAULT_MAX_INFLIGHT_PER_SESSION,
        ),
        ocr_allow_paths=_as_path_tuple(values.get("ocr_allow_paths")),
        log_level=normalize_log_level(str(values["log_level"] or _DEFAULT_LOG_LEVEL)),
    )
    settings.validate()
    return settings
