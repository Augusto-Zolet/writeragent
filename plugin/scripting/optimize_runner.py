# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared trusted optimization execution for Calc tools and Run Python Script."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from plugin.calc.bridge import CalcBridge
from plugin.calc.venv_python import _resolve_python_data
from plugin.doc.document_helpers import is_calc
from plugin.scripting.client import run_optimize
from plugin.framework.errors import ToolExecutionError
from plugin.scripting.optimize_common import HELPER_NAMES

if TYPE_CHECKING:
    from plugin.framework.tool import ToolContext


def calc_tool_context(uno_ctx: Any, doc: Any) -> ToolContext:
    """Minimal ToolContext-like object for range reads on the main thread."""
    from types import SimpleNamespace

    return cast(
        "ToolContext",
        SimpleNamespace(ctx=uno_ctx, doc=doc, doc_type="calc" if is_calc(doc) else None, active_domain=None),
    )


def run_trusted_optimize(
    uno_ctx: Any,
    doc: Any,
    *,
    helper: str,
    params: dict[str, Any] | None = None,
    data_range: str | None = None,
    data: Any = None,
    headers: bool = True,
    task_hint: str | None = None,
) -> dict[str, Any]:
    """Fetch Calc data and run a trusted optimization helper in the user venv."""
    name = str(helper or "").strip()
    if not name:
        raise ToolExecutionError("helper is required", code="OPTIMIZE_ERROR")
    if name not in HELPER_NAMES:
        raise ToolExecutionError(f"Unknown helper {name!r}", code="OPTIMIZE_ERROR")

    dr = str(data_range).strip() if data_range else None
    if not dr and data is None:
        raise ToolExecutionError("Provide data_range or data", code="OPTIMIZE_ERROR")

    tool_ctx = calc_tool_context(uno_ctx, doc)
    py_data, err = _resolve_python_data(tool_ctx, data_range=dr, data=data)
    if err:
        raise ToolExecutionError(err, code="OPTIMIZE_ERROR")
    if py_data is None:
        raise ToolExecutionError("No data to optimize", code="OPTIMIZE_ERROR")

    spec: dict[str, Any] = {"helper": name, "headers": bool(headers)}
    if isinstance(params, dict) and params:
        spec["params"] = params

    context: dict[str, Any] = {}
    try:
        bridge = CalcBridge(doc)
        context["sheet_name"] = bridge.get_active_sheet().getName()
    except Exception:
        pass
    if task_hint:
        context["task_hint"] = str(task_hint)
    if dr:
        context["range_a1"] = dr

    return run_optimize(uno_ctx, spec, py_data, context=context or None)
