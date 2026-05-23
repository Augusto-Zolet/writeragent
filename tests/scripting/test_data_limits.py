# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Tests for scripting.python_max_data_cells limits."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.scripting.data_limits import (
    configured_python_max_data_cells,
    python_max_data_cells_default,
    python_max_data_cells_max,
    python_max_data_cells_min,
)


def test_schema_limits_from_manifest():
    assert python_max_data_cells_default() == 250_000
    assert python_max_data_cells_min() == 1000
    assert python_max_data_cells_max() == 2_000_000


@patch("plugin.framework.config.get_config_int", return_value=250_000)
def test_configured_python_max_data_cells(mock_get):
    ctx = MagicMock()
    assert configured_python_max_data_cells(ctx) == 250_000
    mock_get.assert_called_once_with(ctx, "scripting.python_max_data_cells")


@patch("plugin.framework.config.get_config_int", return_value=9_999_999)
def test_configured_python_max_data_cells_clamps_high(mock_get):
    ctx = MagicMock()
    assert configured_python_max_data_cells(ctx) == 2_000_000


@patch("plugin.framework.config.get_config_int", return_value=0)
def test_configured_python_max_data_cells_clamps_low(mock_get):
    ctx = MagicMock()
    assert configured_python_max_data_cells(ctx) == 1000


def test_settings_field_specs_include_python_max_data_cells():
    from plugin.chatbot.settings_dialog import get_settings_field_specs

    names = {f["name"] for f in get_settings_field_specs(MagicMock())}
    assert "scripting__python_max_data_cells" in names
