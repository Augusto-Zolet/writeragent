# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unexpected MCP tool exceptions must not become opaque INTERNAL_ERROR."""
import json
from unittest.mock import MagicMock, patch

from plugin.mcp.mcp_protocol import MCPProtocolHandler


def test_unexpected_tool_exception_is_tool_execution_error_with_full_message():
    services = MagicMock()
    services.get.return_value = None
    services.tools.get.return_value = None
    handler = MCPProtocolHandler(services)
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
