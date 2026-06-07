# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Host-side optimize RPC — routes trusted helpers to the warm venv worker."""
from __future__ import annotations

from typing import Any

from plugin.framework.errors import ToolExecutionError
from plugin.scripting.config_limits import configured_python_exec_timeout
from plugin.scripting.venv_worker import run_code_in_user_venv

_OPTIMIZE_SESSION_PREFIX = "writeragent:optimize"
_OPTIMIZE_STUB = """\
from plugin.scripting.optimize import run_optimize as _run
result = _run(data["spec"], data.get("data"), data.get("context") or {})
"""


def _optimize_session_id() -> str:
    return _OPTIMIZE_SESSION_PREFIX


def run_optimize(
    ctx: Any,
    spec: dict[str, Any] | str,
    data: Any = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a trusted optimize helper in the user venv via fixed stub."""
    timeout_sec = configured_python_exec_timeout(ctx)
    payload: dict[str, Any] = {"spec": spec, "data": data, "context": context or {}}
    response = run_code_in_user_venv(
        ctx,
        _OPTIMIZE_STUB,
        data=payload,
        timeout_sec=timeout_sec,
        session_id=_optimize_session_id(),
    )
    if response.get("status") != "ok":
        message = str(response.get("message") or "Optimization worker failed.")
        raise ToolExecutionError(message, code="OPTIMIZE_ERROR", details={"worker": response})
    result = response.get("result")
    if not isinstance(result, dict):
        raise ToolExecutionError(
            "Optimization worker returned an unexpected result.",
            code="OPTIMIZE_ERROR",
            details={"result_type": type(result).__name__},
        )
    return result
