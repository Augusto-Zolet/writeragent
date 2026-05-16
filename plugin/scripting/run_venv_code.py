# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Run user Python via subprocess: configured venv, or ``sys.executable`` when venv path is empty (no UNO in child)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, Tuple

from plugin.framework.config import get_config_str
from plugin.scripting.venv_probe import resolve_libreoffice_python, resolve_venv_python

log = logging.getLogger(__name__)

_RESULT_PREFIX = "__WRITERAGENT_VENV_RESULT__"
_BLOCKED_ENV_SUBSTR = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL")


def scrub_subprocess_env(base: dict[str, str] | None) -> dict[str, str]:
    """Drop likely-secret vars from the environment passed to venv Python."""
    if not base:
        return {}
    out: dict[str, str] = {}
    for k, v in base.items():
        ku = k.upper()
        if any(s in ku for s in _BLOCKED_ENV_SUBSTR):
            continue
        out[k] = v
    out.setdefault("PYTHONIOENCODING", "utf-8")
    out.setdefault("PYTHONUTF8", "1")
    out.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return out


def _build_runner_script(user_code: str) -> str:
    """Append a trailer so ``result`` (or ``_``) is emitted as JSON after user code."""
    return (
        user_code.rstrip()
        + "\n\nimport json as _json\n"
        + "_wa = locals().get('result', locals().get('_'))\n"
        + f"print('{_RESULT_PREFIX}' + _json.dumps(_wa, default=str))\n"
    )


def _parse_stdout_for_result(stdout: str) -> Tuple[Any, str]:
    """Return (parsed_result_or_None, unconsumed_stdout_tail)."""
    if not stdout:
        return None, ""
    for line in stdout.splitlines():
        if _RESULT_PREFIX in line:
            idx = line.index(_RESULT_PREFIX) + len(_RESULT_PREFIX)
            payload = line[idx:].strip()
            try:
                return json.loads(payload), stdout
            except json.JSONDecodeError:
                log.warning("venv run: bad JSON after sentinel: %s", payload[:200])
                return None, stdout
    return None, stdout


def run_code_in_user_venv(
    uno_ctx: Any,
    code: str,
    *,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    """Execute *code* in the configured venv, or in ``sys.executable`` when the venv path is empty."""
    if not (code or "").strip():
        return {"status": "error", "message": "No code provided."}

    venv_dir = get_config_str(uno_ctx, "scripting.python_venv_path").strip()
    if venv_dir:
        exe = resolve_venv_python(venv_dir)
        if not exe:
            return {
                "status": "error",
                "message": f"No python executable found under configured venv: {venv_dir!r}",
            }
        log.debug("run_venv_code: using venv interpreter under %s", venv_dir)
    else:
        exe = resolve_libreoffice_python()
        if not exe:
            return {
                "status": "error",
                "message": (
                    "Could not resolve a Python interpreter (sys.executable missing, not a file, or not executable). "
                    "Set scripting.python_venv_path in Settings → Python for a dedicated venv, or fix the LibreOffice install."
                ),
            }
        log.debug("run_venv_code: using process interpreter %s (no venv path set)", exe)

    if timeout_sec < 1:
        timeout_sec = 1
    if timeout_sec > 600:
        timeout_sec = 600

    script_body = _build_runner_script(code)
    child_env = scrub_subprocess_env(dict(os.environ))

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(script_body)
            tmp_path = tmp.name
    except OSError as e:
        return {"status": "error", "message": f"Could not create temp script: {e}"}

    try:
        proc = subprocess.run(
            [exe, tmp_path],
            capture_output=True,
            text=True,
            timeout=float(timeout_sec),
            env=child_env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Timed out after {timeout_sec}s."}
    except OSError as e:
        return {"status": "error", "message": f"Failed to spawn Python: {e}"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    stderr = (proc.stderr or "").strip()
    stdout = proc.stdout or ""

    if proc.returncode != 0:
        tail = stderr or stdout.strip()
        tail = tail[:800] + ("…" if len(tail) > 800 else "")
        msg = f"Python exited with code {proc.returncode}."
        if tail:
            msg = f"{msg}\n{tail}"
        return {"status": "error", "message": msg, "stdout": stdout.strip(), "stderr": stderr}

    parsed, _ = _parse_stdout_for_result(stdout)
    return {
        "status": "ok",
        "result": parsed,
        "stdout": stdout.strip(),
        "stderr": stderr,
    }
