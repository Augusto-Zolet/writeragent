# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for native-runner progress and CLI filter helpers."""

from __future__ import annotations

from pathlib import Path

from plugin.testing_runner import (
    _cli_filters,
    _module_matches_filters,
    _test_function_filters,
)


def test_test_function_filters_skips_module_path_tokens() -> None:
    assert _test_function_filters(["test_cells_uno", "tests/calc/foo.py"]) == []
    assert _test_function_filters(["test_read_range_format_info_performance"]) == [
        "test_read_range_format_info_performance"
    ]


def test_module_matches_filters_by_path_or_def_name(tmp_path: Path) -> None:
    path = tmp_path / "test_cells_uno.py"
    path.write_text("def test_read_range_format_info_performance(ctx, doc):\n    return\n", encoding="utf-8")
    full = str(path)
    assert _module_matches_filters(full, path.name, ["test_cells_uno"]) is True
    assert _module_matches_filters(full, path.name, ["test_read_range_format_info_performance"]) is True
    assert _module_matches_filters(full, path.name, ["test_unrelated_other"]) is False


def test_cli_filters_default_empty() -> None:
    assert isinstance(_cli_filters, list)
