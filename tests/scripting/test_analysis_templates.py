# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for built-in analysis script templates."""

from __future__ import annotations

from plugin.scripting.analysis import (
    HELPER_NAMES,
    ANALYSIS_HEADER_PREFIX,
    get_analysis_script_templates,
    parse_analysis_script_header,
)


def test_templates_cover_all_helpers():
    templates = get_analysis_script_templates()
    assert set(templates.keys()) == set(HELPER_NAMES)


def test_parse_header_round_trip():
    templates = get_analysis_script_templates()
    code = templates["describe_data"]
    assert ANALYSIS_HEADER_PREFIX in code
    meta = parse_analysis_script_header(code)
    assert meta is not None
    assert meta.helper == "describe_data"
    assert meta.params == {}


def test_parse_header_with_params():
    code = '# writeragent:analysis helper=kpi_summary params={"metrics":["Revenue"]}\nresult = 1\n'
    meta = parse_analysis_script_header(code)
    assert meta is not None
    assert meta.helper == "kpi_summary"
    assert meta.params == {"metrics": ["Revenue"]}


def test_parse_header_rejects_unknown_helper():
    code = "# writeragent:analysis helper=not_real params={}\n"
    assert parse_analysis_script_header(code) is None
