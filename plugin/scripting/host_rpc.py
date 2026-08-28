# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-side handlers for venv → LibreOffice tool RPC.

The wire format is the existing Pickle5 frame already used by ppt-master:
``{"type": "tool_call", "id": ..., "tool": ..., "args": {...}}``. The child
writes it on stdout; ``PythonWorkerManager`` replies on stdin. No extra
protocol is added here.

``python_tool_domain`` is host-only (never sent to the child):
- ``None`` — Run Python Script / chat: every registered tool except recursion.
- ``""`` — ``=PY()`` recalc: tool RPC is disabled (formula evaluation must
  stay side-effect free).
- a domain name — allow only that domain's proxies plus ``list_open_documents``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from plugin.scripting.ipc import pack_pickle_frame

log = logging.getLogger(__name__)

# ``run_venv_python_script`` would re-enter the same warm worker while
# ``_io_lock`` is held and deadlock the pipe.
_BLOCKED_FROM_VENV = frozenset({"run_venv_python_script"})

# Host sentinel: disable venv → LO tool RPC (Calc ``=PY()`` recalc).
TOOL_RPC_DISABLED = ""

# ``get_active_document_type()`` always needs this, even in a scoped domain.
_ALWAYS_ALLOWED = frozenset({"list_open_documents"})


def resolve_allowed_tools(python_tool_domain: str | None) -> frozenset[str] | None:
    """Return an allowlist, ``None`` (unrestricted minus blocked), or empty (disabled)."""
    if python_tool_domain is None:
        return None
    if python_tool_domain == TOOL_RPC_DISABLED:
        return frozenset()
    try:
        from plugin.scripting.writeragent_api import DOMAIN_TOOLS
    except ImportError:
        # LibrePy omits the generated proxy; there is nothing to allowlist.
        return frozenset()

    names = DOMAIN_TOOLS.get(python_tool_domain)
    if names is None:
        # generate_tool_proxies singularizes "footnotes" → "footnote".
        singular = python_tool_domain
        if python_tool_domain.endswith("s") and python_tool_domain not in ("images", "styles", "forms"):
            singular = python_tool_domain[:-1]
        names = DOMAIN_TOOLS.get(singular)
    return frozenset(names or ()) | _ALWAYS_ALLOWED


def execute_tool(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    caller: str = "script",
    allowed_tools: frozenset[str] | None = None,
) -> Any:
    """Dispatch a registered WriterAgent tool on the LO main thread (UNO-safe)."""
    if tool_name in _BLOCKED_FROM_VENV:
        raise RuntimeError(
            f"Tool {tool_name!r} cannot run from a venv script (it would re-enter the worker)."
        )
    if allowed_tools is not None and tool_name not in allowed_tools:
        if not allowed_tools:
            raise RuntimeError(
                "Document tool RPC is disabled during =PY() recalculation. "
                "Use Run Python Script… to call writeragent tools."
            )
        raise RuntimeError(
            f"Tool {tool_name!r} is not available in this Python tool domain."
        )

    payload = args if isinstance(args, dict) else {}

    def _run() -> Any:
        try:
            from plugin.doc.doc_type import is_calc, is_draw, is_writer
            from plugin.framework.tool import ToolContext
            from plugin.framework.uno_context import get_active_document, get_ctx
            from plugin.main import get_tools
        except ImportError as exc:
            raise RuntimeError(
                "Document tool RPC is not available in this extension build."
            ) from exc

        uno_ctx = get_ctx()
        doc = get_active_document(uno_ctx)
        if not doc:
            raise RuntimeError("No active document found to run tool")
        if is_calc(doc):
            doc_type = "calc"
        elif is_writer(doc):
            doc_type = "writer"
        elif is_draw(doc):
            doc_type = "draw"
        else:
            doc_type = ""
        registry = get_tools()
        tctx = ToolContext(
            doc=doc,
            ctx=uno_ctx,
            doc_type=doc_type,
            services=registry._services,
            caller=caller,
        )
        return registry.execute(tool_name, tctx, **payload)

    from plugin.framework.queue_executor import execute_on_main_thread

    return execute_on_main_thread(_run)


def handle_tool_call_frame(
    response: dict[str, Any],
    *,
    stdin_write: Callable[[bytes], None],
    allowed_tools: frozenset[str] | None = None,
    caller: str = "script",
) -> bool:
    """Handle a worker ``tool_call`` frame. Returns True if the host should keep reading."""
    if not isinstance(response, dict) or response.get("type") != "tool_call":
        return False

    tool_name = response.get("tool")
    if not isinstance(tool_name, str):
        raise RuntimeError(f"Invalid tool_call: {tool_name!r}")
    args = response.get("args") or {}
    call_id = response.get("id")
    try:
        res = execute_tool(
            tool_name,
            args if isinstance(args, dict) else {},
            caller=caller,
            allowed_tools=allowed_tools,
        )
        tool_response = {"status": "ok", "id": call_id, "result": res}
    except Exception as exc:
        log.exception("venv tool_call %s failed", tool_name)
        tool_response = {"status": "error", "id": call_id, "message": str(exc)}
    stdin_write(pack_pickle_frame(tool_response))
    return True
