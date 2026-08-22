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


def test_addin_entrypoint_deadlock_detected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "addin.py"
        p.write_text(
            """
class CalcAddin:
    def py(self, formula):
        self.handle_formula()

    def handle_formula(self):
        from plugin.framework.queue_executor import execute_on_main_thread
        return execute_on_main_thread(lambda: "blocked")
""",
            encoding="utf-8",
        )
        analyzer = DeadlockAnalyzer(Path(tmp_dir))
        hazards = analyzer.find_deadlock_hazards()
        assert hazards
        assert any("py" in h.entrypoint for h in hazards)
        assert any(h.blocking_op == "execute_on_main_thread" for h in hazards)


def test_nodeadlock_suppression_comment():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "suppressed.py"
        p.write_text(
            """
class CustomAddin:
    def py(self, formula):  # nodeadlock: audited safe path
        self.do_action()

    def do_action(self):
        from plugin.framework.queue_executor import execute_on_main_thread
        return execute_on_main_thread(lambda: "ok")
""",
            encoding="utf-8",
        )
        analyzer = DeadlockAnalyzer(Path(tmp_dir))
        hazards = analyzer.find_deadlock_hazards()
        assert not hazards


def test_class_aware_resolution_prevents_false_collision():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "classes.py"
        p.write_text(
            """
class SafeAddin:
    def py(self, code):
        self.step()

    def step(self):
        return "safe in SafeAddin"

class OtherClass:
    def step(self):
        from plugin.framework.queue_executor import execute_on_main_thread
        return execute_on_main_thread(lambda: 1)
""",
            encoding="utf-8",
        )
        analyzer = DeadlockAnalyzer(Path(tmp_dir))
        hazards = analyzer.find_deadlock_hazards()
        # SafeAddin.py -> SafeAddin.step does NOT call execute_on_main_thread
        assert not hazards


def test_production_plugin_has_no_deadlock_cycles():
    analyzer = DeadlockAnalyzer(Path("plugin"))
    hazards = analyzer.find_deadlock_hazards()
    assert not hazards, f"Found unexpected deadlock hazards in plugin/: {hazards}"

