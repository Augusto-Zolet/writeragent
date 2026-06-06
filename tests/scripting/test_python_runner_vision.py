# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for Run Python Script vision fast path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.scripting.python_runner import execute_and_insert_result
from plugin.scripting.vision_templates import get_vision_script_templates
from plugin.tests.testing_utils import setup_uno_mocks

setup_uno_mocks()


@patch("plugin.scripting.python_runner.insert_content_at_position")
@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_fast_path(mock_run, mock_insert):
    ctx = MagicMock()
    doc = MagicMock()

    with patch("plugin.scripting.python_runner.is_writer", return_value=True), patch(
        "plugin.scripting.python_runner.is_calc", return_value=False
    ), patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=True):
        mock_run.return_value = {
            "status": "ok",
            "helper": "extract_text",
            "full_text": "line1\nline2",
            "metrics": {"line_count": 2},
        }
        code = get_vision_script_templates()["extract_text"]
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is True
    assert "extract_text" in outcome["status_ok_text"]
    assert "2 lines" in outcome["status_ok_text"]
    mock_run.assert_called_once()
    mock_insert.assert_called_once_with(doc, ctx, "line1\nline2", "selection")


@patch("plugin.calc.vision_egress.insert_vision_result_into_calc")
@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_fast_path_calc(mock_run, mock_insert):
    ctx = MagicMock()
    doc = MagicMock()
    mock_insert.return_value = 5

    with patch("plugin.scripting.python_runner.is_writer", return_value=False), patch(
        "plugin.scripting.python_runner.is_calc", return_value=True
    ), patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=True):
        mock_run.return_value = {
            "status": "ok",
            "helper": "extract_text",
            "full_text": "line1\nline2",
            "metrics": {"line_count": 2},
        }
        code = get_vision_script_templates()["extract_text"]
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is True
    assert "extract_text" in outcome["status_ok_text"]
    assert "5 rows" in outcome["status_ok_text"]
    mock_run.assert_called_once()
    mock_insert.assert_called_once_with(doc, ctx, mock_run.return_value)


@patch("plugin.scripting.python_runner.insert_content_at_position")
@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_structure_writer(mock_run, mock_insert):
    ctx = MagicMock()
    doc = MagicMock()

    with patch("plugin.scripting.python_runner.is_writer", return_value=True), patch(
        "plugin.scripting.python_runner.is_calc", return_value=False
    ), patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=True):
        mock_run.return_value = {
            "status": "ok",
            "helper": "extract_structure",
            "full_text": "A\tB\n1\t2",
            "metrics": {"block_count": 2, "table_count": 1},
            "tables": [{"name": "table_1", "columns": ["A", "B"], "rows": [["1", "2"]]}],
            "blocks": [],
            "warnings": [],
        }
        code = get_vision_script_templates()["extract_structure"]
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is True
    assert "extract_structure" in outcome["status_ok_text"]
    assert "tables" in outcome["status_ok_text"]
    mock_insert.assert_called_once_with(doc, ctx, "A\tB\n1\t2", "selection")


@patch("plugin.calc.vision_egress.insert_vision_result_into_calc")
@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_structure_calc(mock_run, mock_insert):
    ctx = MagicMock()
    doc = MagicMock()
    mock_insert.return_value = 8

    with patch("plugin.scripting.python_runner.is_writer", return_value=False), patch(
        "plugin.scripting.python_runner.is_calc", return_value=True
    ), patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=True):
        mock_run.return_value = {
            "status": "ok",
            "helper": "extract_structure",
            "full_text": "",
            "metrics": {"block_count": 0, "table_count": 1},
            "tables": [{"name": "table_1", "columns": ["A"], "rows": [["1"]]}],
            "blocks": [],
            "warnings": [],
        }
        code = get_vision_script_templates()["extract_structure"]
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is True
    assert "8 rows" in outcome["status_ok_text"]
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["params"].get("image_name") == ""


@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_forwards_image_name(mock_run):
    ctx = MagicMock()
    doc = MagicMock()

    with patch("plugin.scripting.python_runner.is_writer", return_value=True), patch(
        "plugin.scripting.vision_runner.supports_vision_manual", return_value=True
    ), patch("plugin.scripting.python_runner.insert_content_at_position"):
        mock_run.return_value = {
            "status": "ok",
            "helper": "extract_text",
            "full_text": "hi",
            "metrics": {"line_count": 1},
        }
        code = '# writeragent:vision helper=extract_text params={"lang":"en","image_name":"Photo1"}\n'
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is True
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["params"]["image_name"] == "Photo1"


@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_rejects_unsupported_doc(mock_run):
    ctx = MagicMock()
    doc = MagicMock()
    code = get_vision_script_templates()["extract_text"]

    with patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=False):
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is False
    assert "Writer or Calc" in outcome["message"]
    mock_run.assert_not_called()


@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_rejects_draw(mock_run):
    ctx = MagicMock()
    doc = MagicMock()
    code = get_vision_script_templates()["extract_text"]

    with patch("plugin.scripting.vision_runner.supports_vision_manual", return_value=False):
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is False
    assert "Writer or Calc" in outcome["message"]
    mock_run.assert_not_called()


@patch("plugin.scripting.vision_runner.run_trusted_vision")
def test_execute_and_insert_vision_surfaces_no_image_selected(mock_run):
    from plugin.framework.errors import ToolExecutionError

    ctx = MagicMock()
    doc = MagicMock()
    code = get_vision_script_templates()["extract_text"]
    mock_run.side_effect = ToolExecutionError("Select an embedded image, then Run again.", code="NO_IMAGE_SELECTED")

    with patch("plugin.scripting.python_runner.is_writer", return_value=True), patch(
        "plugin.scripting.vision_runner.supports_vision_manual", return_value=True
    ):
        outcome = execute_and_insert_result(ctx, doc, code)

    assert outcome["ok"] is False
    assert "embedded image" in outcome["message"]
