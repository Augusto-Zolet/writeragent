# WriterAgent tests — AST-based debug code stripping
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from pathlib import Path
from scripts.strip_code import should_skip_strip, strip_production_code


def test_should_skip_strip() -> None:
    assert should_skip_strip("plugin/testing_runner.py") is True
    assert should_skip_strip("plugin/tests/test_foo.py") is True
    assert should_skip_strip("tests/test_bar.py") is True
    assert should_skip_strip("plugin/contrib/smolagents/monitoring.py") is True
    assert should_skip_strip("plugin/framework/config.py") is False
    assert should_skip_strip("plugin/main.py") is False


def test_strip_production_code_removes_debug(tmp_path: Path) -> None:
    # 1. Create a mock Python file in a temp directory
    test_file = tmp_path / "mock_file.py"
    original_code = (
        "def hello():\n"
        "    print('hello world')\n"
        "    log.debug('debugging trace')\n"
        "    logger.info('info trace')\n"
        "    grammar_obs('observation')\n"
        "    _grammar_obs('internal observation')\n"
        "    return 42\n"
    )
    test_file.write_text(original_code, encoding="utf-8")

    # 2. Run stripping
    strip_production_code(str(tmp_path), dry_run=False)

    # 3. Read it back and assert it is stripped correctly
    stripped_code = test_file.read_text(encoding="utf-8")
    expected_code = (
        "def hello():\n"
        "    return 42\n"
    )
    assert stripped_code == expected_code


def test_strip_production_code_keeps_pass_when_needed(tmp_path: Path) -> None:
    # 1. Create a mock Python file where stripping print leaves an empty block
    test_file = tmp_path / "mock_file.py"
    original_code = (
        "if True:\n"
        "    print('empty block')\n"
    )
    test_file.write_text(original_code, encoding="utf-8")

    # 2. Run stripping
    strip_production_code(str(tmp_path), dry_run=False)

    # 3. Read back and check it inserted a 'pass' statement
    stripped_code = test_file.read_text(encoding="utf-8")
    assert "pass" in stripped_code


def test_strip_production_code_dry_run(tmp_path: Path) -> None:
    # 1. Create a mock Python file
    test_file = tmp_path / "mock_file.py"
    original_code = (
        "def hello():\n"
        "    print('hello world')\n"
        "    return 42\n"
    )
    test_file.write_text(original_code, encoding="utf-8")

    # 2. Run stripping in dry_run mode
    strip_production_code(str(tmp_path), dry_run=True)

    # 3. Read back and assert no changes were written
    code = test_file.read_text(encoding="utf-8")
    assert code == original_code


def test_strip_deal_decorators_and_imports(tmp_path: Path) -> None:
    # 1. Create a mock Python file with deal contracts and fallback imports
    test_file = tmp_path / "mock_file.py"
    original_code = (
        "try:\n"
        "    import deal\n"
        "except ImportError:\n"
        "    class _DummyDeal:\n"
        "        def __getattr__(self, name):\n"
        "            return lambda *args, **kwargs: lambda f: f\n"
        "    deal = _DummyDeal()\n"
        "\n"
        "import math\n"
        "\n"
        "@deal.pre(lambda x: x > 0)\n"
        "@deal.post(lambda r: r is not None)\n"
        "def some_function(x):\n"
        "    return math.sqrt(x)\n"
        "\n"
        "@deal.pure\n"
        "async def some_async_func():\n"
        "    return 42\n"
    )
    test_file.write_text(original_code, encoding="utf-8")

    # 2. Run stripping
    strip_production_code(str(tmp_path), dry_run=False)

    # 3. Read it back and assert it is stripped correctly
    stripped_code = test_file.read_text(encoding="utf-8")
    expected_code = (
        "\n"
        "import math\n"
        "\n"
        "def some_function(x):\n"
        "    return math.sqrt(x)\n"
        "\n"
        "async def some_async_func():\n"
        "    return 42\n"
    )
    assert stripped_code == expected_code
