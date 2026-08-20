# WriterAgent - Tests for Static Deadlock & Thread Transition Analyzer
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for scripts/analyze_thread_deadlocks.py."""

import tempfile
from pathlib import Path

from scripts.analyze_thread_deadlocks import DeadlockAnalyzer


def test_clean_directory_passes():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "mod.py"
        p.write_text(
            """
def execute_python_addin(ctx, code):
    return "ok"
""",
            encoding="utf-8",
        )
        analyzer = DeadlockAnalyzer(Path(tmp_dir))
        hazards = analyzer.find_deadlock_hazards()
        assert not hazards


def test_deadlock_hazard_cycle_detected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "mod.py"
        p.write_text(
            """
def execute_python_addin(ctx, code):
    return helper(ctx)

def helper(ctx):
    from plugin.framework.queue_executor import execute_on_main_thread
    return execute_on_main_thread(lambda: 123)
""",
            encoding="utf-8",
        )
        analyzer = DeadlockAnalyzer(Path(tmp_dir))
        hazards = analyzer.find_deadlock_hazards()
        assert hazards
        assert any(h.entrypoint == "execute_python_addin" for h in hazards)
        assert any(h.blocking_op == "execute_on_main_thread" for h in hazards)


def test_production_plugin_has_no_deadlock_cycles():
    analyzer = DeadlockAnalyzer(Path("plugin"))
    hazards = analyzer.find_deadlock_hazards()
    assert not hazards, f"Found unexpected deadlock hazards in plugin/: {hazards}"
