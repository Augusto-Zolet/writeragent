# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unexpected MCP tool exceptions must not become opaque INTERNAL_ERROR."""
import json
from unittest.mock import MagicMock, patch

from plugin.mcp.mcp_protocol import MCPProtocolHandler


def _handler():
    services = MagicMock()
    services.get.return_value = None
    services.tools.get.return_value = None
    return MCPProtocolHandler(services)


def test_unexpected_tool_exception_is_tool_execution_error_with_full_message():
    handler = _handler()
    boom = RuntimeError("max index out of range in table cell")
    with patch.object(handler, "_execute_with_backpressure", side_effect=boom):
        result = handler._mcp_tools_call(
            {"name": "apply_style", "arguments": {"style": "Heading 1"}},
            document_url=None,
        )
    assert result is not None
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "error"
    assert payload["code"] == "TOOL_EXECUTION_ERROR"
    assert payload["message"] == "max index out of range in table cell"
    assert "INTERNAL_ERROR" not in payload["code"]


def test_writeragent_exception_is_tool_result_not_jsonrpc_internal():
    """tools/call ToolExecutionError must be HTTP 200 + isError, not HTTP 500."""
    from plugin.framework.errors import ToolExecutionError

    handler = _handler()
    boom = ToolExecutionError("max index out of range in table cell")
    with patch.object(handler, "_execute_with_backpressure", side_effect=boom):
        status, body = handler._process_jsonrpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "apply_style", "arguments": {"style": "Heading 1"}},
        })
    assert status == 200
    result = body["result"]
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["code"] == "TOOL_EXECUTION_ERROR"
    assert payload["message"] == "max index out of range in table cell"
    assert "error" not in body or body.get("error") is None
