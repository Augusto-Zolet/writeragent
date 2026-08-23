# WriterAgent - Tests for AST Thread Safety Linter
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for scripts/lint_thread_safety.py."""

import tempfile
from pathlib import Path

from scripts.lint_thread_safety import (
    scan_file,
    scan_target,
)


def _scan_source(source: str, file_name: str = "test_case.py") -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        temp_path = Path(f.name)
    try:
        return scan_file(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def test_clean_guarded_function():
    code = """
from plugin.framework.thread_guard import on_main_thread

def calc_helper(ctx):
    if not on_main_thread():
        return None
    desktop = get_desktop(ctx)
    return desktop
"""
    findings = _scan_source(code, "plugin/calc/python/clean.py")
    assert not findings


def test_clean_main_thread_only_decorator():
    code = """
from plugin.framework.thread_guard import main_thread_only

@main_thread_only
def calc_ui_action(ctx):
    desktop = get_desktop(ctx)
    return desktop
"""
    findings = _scan_source(code, "plugin/calc/python/clean.py")
    assert not findings


def test_unguarded_uno_access_detected():
    code = """
def execute_python_addin(ctx, code):
    desktop = get_desktop(ctx)
    return "ok"
"""
    findings = _scan_source(code, "plugin/calc/python/bad.py")
    assert findings
    assert any(f.rule_id == "unguarded-uno-access" for f in findings)


def test_blocking_marshal_in_sync_dispatch_detected():
    code = """
def execute_python_addin(ctx, code):
    return execute_on_main_thread(lambda: 123)
"""
    findings = _scan_source(code, "plugin/calc/python/bad.py")
    assert findings
    assert any(f.rule_id == "blocking-marshal-in-sync-dispatch" for f in findings)


def test_nested_on_main_thread_guard():
    code = """
from plugin.framework.thread_guard import on_main_thread

def session_key(ctx, code, doc=None):
    target = doc
    if target is None:
        if on_main_thread():
            target = _get_calc_doc(ctx)
    return target
"""
    findings = _scan_source(code, "plugin/calc/python/nested.py")
    assert not findings


def test_production_plugin_calc_python_is_clean():
    target = Path("plugin/calc/python")
    findings = scan_target(target)
    assert not findings, f"Expected no AST lint violations in plugin/calc/python, got: {findings}"
