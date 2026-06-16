# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""``find_tools`` -- MCP discovery meta-tool for the ``direct_discovery`` exposure mode.

The MCP server advertises a small core tool set; the ~100+ specialized tools are
callable by name but hidden from ``tools/list`` to keep it short. ``find_tools`` lets a
client search that hidden catalog by free-text query and/or specialized domain and get
back ready-to-call MCP schemas -- so any MCP client (Claude, Codex, generic) can reach
the full tool set without the delegate sub-agent (no LLM backend) and without bloating
context.

Ranking is host-side lexical (BM25-lite + substring bonus): no venv, no numpy, no
main-thread/UNO hop, so it runs instantly inside ``tools/call`` on any install. A
semantic backend is a clean later upgrade behind the embeddings venv -- ``_rank``'s
signature stays stable.

Only advertised in ``tools/list`` when ``mcp.tool_exposure_mode == "direct_discovery"``
(gated by name in ``plugin/mcp/mcp_protocol.py``); ``tier="mcp"`` keeps it off the chat
agent's tool list.
"""
from __future__ import annotations

import math
import re
from typing import Any

from plugin.framework.tool import ToolBase, ToolContext

_DEFAULT_LIMIT = 8
_MAX_LIMIT = 50
_FINISH_TOOL = "specialized_workflow_finished"
# In direct_discovery mode the delegate gateway is not the intended route, so keep
# its (core-tier) gateway tools out of discovery results.
_GATEWAY_PREFIX = "delegate_to_specialized_"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Dropped from query token scoring (kept for the raw-substring bonus) so common words
# like "a"/"the" don't surface unrelated tools.
_STOPWORDS = frozenset({
    "a", "an", "the", "to", "from", "of", "and", "or", "for", "with", "in", "on",
    "is", "it", "this", "that", "my", "your", "into", "as", "at", "by",
})


def _tokenize(text: Any) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def _doc_tokens(schema: dict) -> list[str]:
    """Searchable token bag for a tool schema: name tokens weighted x3, description x1."""
    name_toks = _tokenize(str(schema.get("name") or "").replace("_", " "))
    body_toks = _tokenize(schema.get("description") or "")
    return name_toks * 3 + body_toks


def _rank(schemas: list[dict], query: str | None, limit: int) -> list[dict]:
    """Rank tool schemas against a free-text query (BM25-lite + substring bonus).

    Deterministic and dependency-free. Empty query -> registry order, truncated to
    ``limit``. With a query, schemas with no token overlap and no raw-substring hit
    score 0 and are dropped. Stable secondary sort by name.
    """
    q = (query or "").strip()
    if not q:
        return schemas[:limit]

    q_all = set(_tokenize(q))
    q_tokens = (q_all - _STOPWORDS) or q_all  # if the query is all stopwords, keep them
    raw_q = q.lower()
    docs = [(s, _doc_tokens(s)) for s in schemas]
    n = len(docs)
    if not n:
        return []
    avgdl = sum(len(d) for _, d in docs) / n or 0.0
    k1, b = 1.2, 0.75
    df = {qt: sum(1 for _, d in docs if qt in d) for qt in q_tokens}

    scored: list[tuple[float, str, dict]] = []
    for schema, d in docs:
        dl = len(d)
        score = 0.0
        for qt in q_tokens:
            f = d.count(qt)
            if not f:
                continue
            n_q = df.get(qt) or 1
            idf = math.log(1 + (n - n_q + 0.5) / (n_q + 0.5))
            denom = f + k1 * (1 - b + b * (dl / avgdl if avgdl else 0.0))
            score += idf * (f * (k1 + 1)) / denom
        name = str(schema.get("name") or "")
        if raw_q in name.lower():
            score += 2.0
        elif raw_q in str(schema.get("description") or "").lower():
            score += 0.5
        if score > 0:
            scored.append((score, name, schema))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [s for _, _, s in scored[:limit]]


def _agent_label_for_doc_type(doc_type: str | None) -> str:
    return {"calc": "Calc", "draw": "Draw", "impress": "Draw",
            "writer": "Writer"}.get((doc_type or "").lower(), "Writer")


def get_domain_guidance(domain: str, *, agent_label: str = "Writer", ctx: Any = None) -> str:
    """Static per-domain usage guidance for direct callers (mirrors the delegate's hints).

    Returns ``""`` for live-context domains (shapes canvas / spreadsheet snapshot /
    open-docs) that require a running document and for unknown domains.
    """
    if domain == "footnotes":
        return ("For footnotes_insert: if the task quotes or names the document anchor "
                "(e.g. a sentence), pass that exact string as insert_after_text so the "
                "note is placed after that text.")
    if domain == "charts":
        if agent_label == "Calc":
            return "When creating a chart in Calc, you MUST specify the data range explicitly (e.g. data_range='A1:B10')."
        return ("When creating or editing a chart in Writer or Draw/Impress, you MUST "
                "specify both the `headers` and `rows` parameters.")
    if domain == "images":
        return ("Discover local image files with list_nearby_image_files before insert_image "
                "when the user refers to a photo in the folder.")
    if domain == "analysis":
        return ("For stats, cleaning, regression, clustering, or simulation on tabular data "
                "use analyze_data; for charts use plot_data (or auto_plot=true); for live "
                "single-cell what-if use calc_goal_seek; for constrained optimization use "
                "calc_solver. Always pass a data_range (A1 address) for bulk data.")
    if domain == "python":
        try:
            from plugin.framework.constants import python_specialized_sub_agent_hint
            return (python_specialized_sub_agent_hint(agent_label) or "").strip()
        except Exception:
            return ""
    if domain == "document_research":
        try:
            from plugin.doc.document_research import get_document_research_workflow_hint
            return (get_document_research_workflow_hint(getattr(ctx, "ctx", None)) or "").strip()
        except Exception:
            return ""
    return ""


class FindTools(ToolBase):
    """Discover registry tools by free-text query and/or specialized domain.

    Returns ready-to-call MCP schemas for tools that are callable by name but hidden
    from the default ``tools/list``. Host-side lexical ranking only -- no venv, no UNO,
    runs inline in ``tools/call``.
    """

    name = "find_tools"
    description = (
        "Discover additional tools that are available but not listed here. This MCP "
        "server exposes a small core tool set; many specialized capabilities (e.g. "
        "footnotes, charts, images, data analysis, document research) are callable by "
        "name but hidden from the default list to keep it short. Call find_tools with a "
        "natural-language `query` describing what you want to do (e.g. \"insert a "
        "footnote\", \"make a bar chart from a range\") to get the matching tools and "
        "their full input schemas, ready to call directly. Pass a `domain` to list every "
        "tool in one area. Call with no arguments to see the available domains and a "
        "sample of tools. Always prefer calling a tool returned by find_tools over giving "
        "up because a capability seems missing."
    )
    tier = "mcp"
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": ("Natural-language description of the task you want to accomplish "
                                "(e.g. 'insert a footnote', 'create a chart from a cell range'). "
                                "Tools are ranked by relevance to it. Optional."),
            },
            "domain": {
                "type": "string",
                "description": ("Optional specialized area to scope results to (e.g. 'footnotes', "
                                "'charts', 'images', 'analysis', 'document_research'). Call "
                                "find_tools with no arguments to see the available domains."),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of tools to return (default 8).",
                "minimum": 1,
                "maximum": _MAX_LIMIT,
            },
        },
        "required": [],
    }

    def execute(self, ctx: ToolContext, query: str | None = None,
                domain: str | None = None, limit: int | None = None,
                **kwargs: Any) -> dict[str, Any]:
        registry = ctx.services.get("tools") if ctx.services else None
        if registry is None:
            return self._tool_error("Tool registry unavailable.", code="SERVICE_UNAVAILABLE")

        # Normalize client-supplied inputs (an MCP client can send anything).
        query = query if isinstance(query, str) else None
        domain = domain if isinstance(domain, str) else None
        try:
            top_n = int(limit) if limit else _DEFAULT_LIMIT
        except (TypeError, ValueError, OverflowError):
            top_n = _DEFAULT_LIMIT
        top_n = max(1, min(top_n, _MAX_LIMIT))

        doc = getattr(ctx, "doc", None)
        domains = self._available_domains(registry, doc)

        if domain:
            # active_domain narrowing: the domain's specialized tools + their required
            # core tools (the registry bypasses tier exclusion when active_domain is set).
            schemas = registry.get_schemas("mcp", doc=doc, active_domain=domain)
        else:
            # global search: surface specialized tiers but hide the mcp tier (so the
            # discovery tools don't return themselves) and the workflow-control tier.
            schemas = registry.get_schemas(
                "mcp", doc=doc, exclude_tiers=frozenset({"mcp", "specialized_control"}))

        # Drop the workflow finish tool (re-added by the domain narrowing) and the
        # delegate gateway tools, and guard against malformed (non-dict) schemas.
        candidates = [
            s for s in (schemas or [])
            if isinstance(s, dict)
            and s.get("name") != _FINISH_TOOL
            and not str(s.get("name") or "").startswith(_GATEWAY_PREFIX)
        ]
        ranked = _rank(candidates, query, top_n)

        result: dict[str, Any] = {
            "status": "ok",
            "query": query,
            "domain": domain,
            "available_domains": domains,
            "tools": ranked,
        }
        if domain:
            guidance = get_domain_guidance(
                domain,
                agent_label=_agent_label_for_doc_type(getattr(ctx, "doc_type", None)),
                ctx=ctx,
            )
            if guidance:
                result["domain_guidance"] = guidance
        return result

    @staticmethod
    def _available_domains(registry: Any, doc: Any) -> list[str]:
        """Distinct specialized domains applicable to the active document, sorted."""
        try:
            tools = registry.get_tools(doc=doc, exclude_tiers=())
        except Exception:
            return []
        return sorted({
            d for t in tools if (d := getattr(t, "specialized_domain", None))
        })
