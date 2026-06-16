# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the find_tools discovery meta-tool + its tools/list gating.

Registry is mocked (the tool's own logic + the protocol gating are what we assert
here); the real registry / domain-narrowing path is covered by the live MCP run.
"""
from unittest.mock import MagicMock

from plugin.doc.find_tools_tool import FindTools, _rank, get_domain_guidance
from plugin.framework.tool import ToolBase, ToolRegistry
from plugin.mcp.mcp_protocol import MCPProtocolHandler
from plugin.writer.specialized_base import ToolWriterSpecialBase


# --------------------------------------------------------------------------- #
# tool metadata + pure ranker
# --------------------------------------------------------------------------- #

def test_find_tools_properties():
    tool = FindTools()
    assert tool.name == "find_tools"
    assert tool.tier == "mcp"           # hidden from the chat agent's tool list
    assert tool.is_mutation is False


def test_rank_name_substring_outranks_description():
    schemas = [
        {"name": "unrelated_tool", "description": "mentions footnote here"},
        {"name": "footnotes_insert", "description": "add a note"},
    ]
    assert _rank(schemas, "footnote", 5)[0]["name"] == "footnotes_insert"


def test_rank_empty_query_returns_input_order_truncated():
    schemas = [{"name": "a", "description": ""}, {"name": "b", "description": ""}]
    assert _rank(schemas, "", 1) == schemas[:1]


def test_rank_no_overlap_is_dropped():
    schemas = [{"name": "footnotes_insert", "description": "add a note"}]
    assert _rank(schemas, "zzz_no_such_capability", 5) == []


def test_rank_multiword_query():
    schemas = [
        {"name": "create_chart", "description": "make a chart from a data range"},
        {"name": "footnotes_insert", "description": "insert a footnote at an anchor"},
        {"name": "noise", "description": "totally unrelated text"},
    ]
    ranked = _rank(schemas, "insert a footnote", 2)
    assert ranked[0]["name"] == "footnotes_insert"


def test_get_domain_guidance():
    assert "data range" in get_domain_guidance("charts", agent_label="Calc").lower()
    assert "headers" in get_domain_guidance("charts", agent_label="Writer").lower()
    assert "insert_after_text" in get_domain_guidance("footnotes")
    assert get_domain_guidance("totally_unknown_domain") == ""


# --------------------------------------------------------------------------- #
# execute() with a mocked registry
# --------------------------------------------------------------------------- #

def _ctx(registry, doc_type="writer"):
    ctx = MagicMock()
    ctx.services.get.side_effect = lambda name: registry if name == "tools" else None
    ctx.doc = MagicMock()
    ctx.doc_type = doc_type
    ctx.ctx = MagicMock()
    return ctx


def _schema(name, desc="a tool"):
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": {}}}


def test_execute_domain_returns_domain_schemas_without_finish_tool():
    registry = MagicMock()
    registry.get_schemas.return_value = [
        _schema("footnotes_insert"), _schema("footnotes_list"),
        _schema("specialized_workflow_finished", "finish"),
    ]
    registry.get_tools.return_value = [
        MagicMock(specialized_domain="footnotes"), MagicMock(specialized_domain=None),
    ]
    ctx = _ctx(registry)

    result = FindTools().execute(ctx, domain="footnotes")

    names = {t["name"] for t in result["tools"]}
    assert {"footnotes_insert", "footnotes_list"} <= names
    assert "specialized_workflow_finished" not in names         # finish tool stripped
    for t in result["tools"]:
        assert "inputSchema" in t
    registry.get_schemas.assert_called_once_with("mcp", doc=ctx.doc, active_domain="footnotes")
    assert "footnotes" in result["available_domains"]
    assert "insert_after_text" in result.get("domain_guidance", "")


def test_execute_query_ranks_top_n():
    registry = MagicMock()
    registry.get_schemas.return_value = [
        _schema("footnotes_insert", "insert a footnote at an anchor"),
        _schema("create_chart", "make a chart from a range"),
        _schema("unrelated", "something else entirely"),
    ]
    registry.get_tools.return_value = []
    ctx = _ctx(registry)

    result = FindTools().execute(ctx, query="insert a footnote", limit=2)

    names = [t["name"] for t in result["tools"]]
    assert len(names) <= 2
    assert names[0] == "footnotes_insert"
    # global branch hides mcp + control tiers
    registry.get_schemas.assert_called_once_with(
        "mcp", doc=ctx.doc, exclude_tiers=frozenset({"mcp", "specialized_control"}))


def test_execute_unknown_query_returns_empty():
    registry = MagicMock()
    registry.get_schemas.return_value = [_schema("footnotes_insert", "add a note")]
    registry.get_tools.return_value = []
    result = FindTools().execute(_ctx(registry), query="zzz_no_such_capability")
    assert result["tools"] == []


def test_execute_no_args_lists_domains():
    registry = MagicMock()
    registry.get_schemas.return_value = [_schema("a"), _schema("b")]
    registry.get_tools.return_value = [
        MagicMock(specialized_domain="footnotes"), MagicMock(specialized_domain="charts"),
    ]
    result = FindTools().execute(_ctx(registry))
    assert sorted(result["available_domains"]) == ["charts", "footnotes"]
    assert result["tools"]                                       # global listing, no query


def test_execute_no_registry_errors():
    ctx = MagicMock()
    ctx.services.get.side_effect = lambda name: None
    result = FindTools().execute(ctx)
    assert result.get("status") == "error"


# --------------------------------------------------------------------------- #
# tools/list gating: find_tools only in direct_discovery
# --------------------------------------------------------------------------- #

def _handler(mode, schemas):
    services = MagicMock()
    services.tools.get_schemas.return_value = list(schemas)
    services.config.get.side_effect = (
        lambda key, default=None: mode if key == "mcp.tool_exposure_mode" else default
    )
    services.get.side_effect = lambda name: getattr(services, name, None)

    def _inline(fn, *a, **k):
        k.pop("timeout", None)
        return fn(*a, **k)

    services.main_thread.execute.side_effect = _inline
    services.document.get_active_document.return_value = MagicMock()
    return MCPProtocolHandler(services)


def _list_names(mode):
    schemas = [
        {"name": "find_tools", "description": "discovery", "inputSchema": {}},
        {"name": "insert_footnote", "description": "footnote", "inputSchema": {}},
        {"name": "apply_document_content", "description": "core", "inputSchema": {}},
    ]
    handler = _handler(mode, schemas)
    return {t["name"] for t in handler._mcp_tools_list({})["tools"]}


def test_find_tools_listed_only_in_direct_discovery():
    assert "find_tools" not in _list_names("delegate")
    assert "find_tools" not in _list_names("direct_flat")
    assert "find_tools" in _list_names("direct_discovery")


def test_gating_keeps_other_tools():
    # the name filter only drops find_tools, never the real tools
    assert "apply_document_content" in _list_names("delegate")
    assert "insert_footnote" in _list_names("direct_discovery")


# --------------------------------------------------------------------------- #
# real-registry tests: validate the FindTools <-> ToolRegistry contract and the
# per-mode tools/list sizing (the actual product promise) without mocking the
# registry internals. Universal (uno_services=None) fakes so no live doc is needed.
# --------------------------------------------------------------------------- #

class _FtBase(ToolWriterSpecialBase):
    # _is_specialized_domain_tool requires an instance of the real specialized base
    # (tool.py:435), not just a specialized_domain attribute. uno_services=None keeps
    # the fakes universal so the test needs no live Writer document.
    specialized_domain = "footnotes"
    uno_services = None
    is_mutation = False
    description = "footnotes domain tool"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


class _FtInsert(_FtBase):
    name = "footnotes_insert"
    description = "insert a footnote at an anchor"


class _FtList(_FtBase):
    name = "footnotes_list"
    description = "list the footnotes in the document"


class _FinishTool(ToolBase):
    name = "specialized_workflow_finished"
    description = "finish the specialized workflow"
    tier = "specialized_control"
    is_mutation = False
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, ctx, **kwargs):
        return {}


class _GatewayTool(ToolBase):
    name = "delegate_to_specialized_writer_toolset"
    description = "delegate to a specialized writer toolset"
    tier = "core"
    is_mutation = False
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, ctx, **kwargs):
        return {}


class _CoreTool(ToolBase):
    name = "apply_document_content"
    description = "core document edit"
    tier = "core"
    is_mutation = False
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, ctx, **kwargs):
        return {}


def _real_registry():
    reg = ToolRegistry(MagicMock())
    for cls in (FindTools, _FtInsert, _FtList, _FinishTool, _GatewayTool, _CoreTool):
        reg.register(cls())
    return reg


def _ctx_real(registry):
    ctx = MagicMock()
    ctx.services.get.side_effect = lambda name: registry if name == "tools" else None
    ctx.doc = None          # universal fakes pass with no active document
    ctx.doc_type = "writer"
    ctx.ctx = MagicMock()
    return ctx


def _handler_real(mode, registry):
    services = MagicMock()
    services.tools = registry
    services.config.get.side_effect = (
        lambda key, default=None: mode if key == "mcp.tool_exposure_mode" else default
    )
    services.get.side_effect = lambda name: getattr(services, name, None)

    def _inline(fn, *a, **k):
        k.pop("timeout", None)
        return fn(*a, **k)

    services.main_thread.execute.side_effect = _inline
    services.document.get_active_document.return_value = None
    return MCPProtocolHandler(services)


def test_execute_domain_real_registry():
    result = FindTools().execute(_ctx_real(_real_registry()), domain="footnotes")
    names = {t["name"] for t in result["tools"]}
    assert {"footnotes_insert", "footnotes_list"} <= names
    assert "specialized_workflow_finished" not in names      # finish stripped
    assert "delegate_to_specialized_writer_toolset" not in names
    assert "find_tools" not in names                          # self not surfaced


def test_mode_sizing_real_registry():
    reg = _real_registry()

    def names(mode):
        return {t["name"] for t in _handler_real(mode, reg)._mcp_tools_list({})["tools"]}

    spec = {"footnotes_insert", "footnotes_list"}
    delegate = names("delegate")
    assert not (spec & delegate) and "find_tools" not in delegate
    assert "apply_document_content" in delegate
    flat = names("direct_flat")
    assert spec <= flat and "find_tools" not in flat          # specialized exposed, no find_tools
    discovery = names("direct_discovery")
    assert "find_tools" in discovery and not (spec & discovery)  # small list + find_tools


# --------------------------------------------------------------------------- #
# robustness regressions (the review's SHOULD-FIX hardenings)
# --------------------------------------------------------------------------- #

def test_execute_tolerates_malformed_schemas():
    registry = MagicMock()
    registry.get_schemas.return_value = [
        {"name": 123, "description": ["x"], "inputSchema": {}},   # non-string name/desc
        "not_a_dict",                                             # non-dict candidate
        _schema("footnotes_insert", "add a note"),
    ]
    registry.get_tools.return_value = []
    result = FindTools().execute(_ctx(registry), query="footnote")
    assert result["status"] == "ok"


def test_execute_tolerates_infinite_limit():
    registry = MagicMock()
    registry.get_schemas.return_value = [_schema("a")]
    registry.get_tools.return_value = []
    assert FindTools().execute(_ctx(registry), limit=float("inf"))["status"] == "ok"


def test_execute_tolerates_non_string_inputs():
    registry = MagicMock()
    registry.get_schemas.return_value = [_schema("a")]
    registry.get_tools.return_value = []
    assert FindTools().execute(_ctx(registry), query=["not", "str"], domain=123)["status"] == "ok"


def test_execute_excludes_gateway_from_global():
    registry = MagicMock()
    registry.get_schemas.return_value = [
        _schema("delegate_to_specialized_writer_toolset", "delegate"),
        _schema("footnotes_insert", "insert a footnote"),
    ]
    registry.get_tools.return_value = []
    names = {t["name"] for t in FindTools().execute(_ctx(registry), query="footnote")["tools"]}
    assert "delegate_to_specialized_writer_toolset" not in names
