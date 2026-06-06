# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Threading tests for specialized delegation setup (UNO on main thread)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.calc.base import ToolCalcAnalysisBase
from plugin.calc.specialized import DelegateToSpecializedCalc
from plugin.contrib.smolagents.memory import FinalAnswerStep
from plugin.framework.tool import ToolRegistry
from plugin.tests.testing_utils import setup_uno_mocks

setup_uno_mocks()


class _DummyAnalysisTool(ToolCalcAnalysisBase):
    name = "dummy_analysis_tool"
    description = "test"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, ctx, **kwargs):
        return {"status": "ok"}


@patch("plugin.doc.specialized_base.USE_SUB_AGENT", True)
@patch(
    "plugin.chatbot.smol_agent.get_config_int",
    side_effect=lambda _ctx, key: 25 if key == "chatbot.max_tool_rounds" else 1024,
)
@patch("plugin.chatbot.smol_agent.get_api_config", create=True, return_value={"model": "test/model"})
@patch("plugin.chatbot.smol_agent.ToolCallingAgent")
@patch("plugin.chatbot.smol_agent.WriterAgentSmolModel")
@patch("plugin.chatbot.smol_agent.LlmClient")
@patch("plugin.framework.queue_executor.execute_on_main_thread")
@patch("plugin.doc.document_helpers.get_calc_context_for_chat")
def test_calc_delegate_marshals_spreadsheet_context_to_main_thread(
    mock_get_calc_context,
    mock_execute_on_main,
    _mock_llm,
    _mock_smol_model,
    mock_agent_class,
    _mock_get_config,
    _mock_get_config_int,
):
    mock_get_calc_context.return_value = "Sheets: Sheet1\nActive Sheet: Sheet1"
    mock_execute_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    mock_agent_instance = MagicMock()
    mock_agent_instance.run.return_value = [FinalAnswerStep(output="done")]
    mock_agent_class.return_value = mock_agent_instance

    registry = ToolRegistry(MagicMock())
    registry.register(_DummyAnalysisTool())
    registry.register(DelegateToSpecializedCalc())

    mock_doc = MagicMock()
    mock_doc.supportsService.return_value = True

    ctx = MagicMock()
    ctx.services = {"tools": registry}
    ctx.doc = mock_doc
    ctx.ctx = MagicMock()
    ctx.doc_type = "calc"
    ctx.stop_checker = lambda: False

    gateway = registry.get("delegate_to_specialized_calc_toolset")
    result = gateway.execute_safe(ctx, domain="analysis", task="Describe sales data")

    assert result["status"] == "ok"
    mock_execute_on_main.assert_called()
    mock_get_calc_context.assert_called_once_with(mock_doc, ctx=ctx.ctx)

    instructions = mock_agent_class.call_args.kwargs["instructions"]
    assert "[SPREADSHEET CONTEXT]" in instructions
    assert "Sheets: Sheet1" in instructions
