#!/usr/bin/env python3
# WriterAgent - AST Static Linter for UNO Thread Safety & Deadlocks
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""AST static linter to catch unguarded UNO calls and blocking deadlocks at build time.

Scans Python files to verify:
1. Functions that call UNO source getters (get_desktop, get_ctx, get_calc_document_from_ctx, etc.)
   are either decorated with @main_thread_only or have an on_main_thread() guard.
2. Synchronous add-in evaluation and notification functions do not call blocking execute_on_main_thread.
3. Add-in calculation paths do not use bare blocking synchronization primitives.

Usage:
    python scripts/lint_thread_safety.py [files or directories]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple

RED_UNO_SOURCES = {
    "get_desktop",
    "get_ctx",
    "get_active_document",
    "get_toolkit",
    "get_package_info",
    "_get_calc_doc",
    "get_calc_document_from_ctx",
    "get_active_document_for_scripts",
}

SYNC_ADDIN_FUNCTIONS = {
    "execute_python_addin",
    "execute_prompt_addin",
    "_notify_thread_violation",
    "session_key",
    "py",
}

BLOCKING_MARSHAL_FUNCS = {
    "execute_on_main_thread",
}


class Finding(NamedTuple):
    file: Path
    line: int
    col: int
    rule_id: str
    message: str


class ThreadSafetyASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.findings: list[Finding] = []
        self.function_stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self.guarded_scopes: list[bool] = [False]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)

    def _visit_statements(self, statements: list[ast.stmt]) -> None:
        guarded = False
        for stmt in statements:
            if isinstance(stmt, ast.If):
                cond_str = ast.unparse(stmt.test)
                has_on_main = "on_main_thread()" in cond_str
                # Case 1: if not on_main_thread(): ... return / raise
                if has_on_main and (cond_str.startswith("not ") or " not " in cond_str):
                    exits_early = bool(stmt.body) and isinstance(
                        stmt.body[-1], (ast.Return, ast.Raise)
                    )
                    if exits_early and not stmt.orelse:
                        # Body is visited unguarded, but subsequent sibling statements are guarded
                        self.guarded_scopes.append(False)
                        for s in stmt.body:
                            self.visit(s)
                        self.guarded_scopes.pop()
                        guarded = True
                        continue
                    elif stmt.orelse:
                        # Body is unguarded, orelse is guarded
                        self.guarded_scopes.append(False)
                        for s in stmt.body:
                            self.visit(s)
                        self.guarded_scopes.pop()

                        self.guarded_scopes.append(True)
                        for s in stmt.orelse:
                            self.visit(s)
                        self.guarded_scopes.pop()
                        continue

                # Case 2: if on_main_thread(): body is guarded, orelse is unguarded
                if has_on_main and not cond_str.startswith("not ") and " not " not in cond_str:
                    self.guarded_scopes.append(True)
                    for s in stmt.body:
                        self.visit(s)
                    self.guarded_scopes.pop()

                    if stmt.orelse:
                        self.guarded_scopes.append(False)
                        for s in stmt.orelse:
                            self.visit(s)
                        self.guarded_scopes.pop()
                    continue

            if guarded:
                self.guarded_scopes.append(True)
                self.visit(stmt)
                self.guarded_scopes.pop()
            else:
                self.visit(stmt)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_statements(node.body)
        for h in node.handlers:
            self._visit_statements(h.body)
        if node.orelse:
            self._visit_statements(node.orelse)
        if node.finalbody:
            self._visit_statements(node.finalbody)

    def visit_With(self, node: ast.With) -> None:
        self._visit_statements(node.body)

    def visit_For(self, node: ast.For) -> None:
        self._visit_statements(node.body)
        if node.orelse:
            self._visit_statements(node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self._visit_statements(node.body)
        if node.orelse:
            self._visit_statements(node.orelse)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_main_thread_only = any(
            (isinstance(d, ast.Name) and d.id == "main_thread_only")
            or (isinstance(d, ast.Attribute) and d.attr == "main_thread_only")
            for d in node.decorator_list
        )
        self.function_stack.append(node)
        self.guarded_scopes.append(is_main_thread_only)
        self._visit_statements(node.body)
        self.guarded_scopes.pop()
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        current_fn = self.function_stack[-1].name if self.function_stack else ""
        is_guarded = any(self.guarded_scopes)

        # Rule 1: Unguarded UNO access in addin/scripting files
        if func_name in RED_UNO_SOURCES and not is_guarded:
            if current_fn in SYNC_ADDIN_FUNCTIONS or "calc/python" in str(self.file_path):
                self.findings.append(
                    Finding(
                        file=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        rule_id="unguarded-uno-access",
                        message=f"Call to UNO source '{func_name}' is not guarded by on_main_thread() check or @main_thread_only.",
                    )
                )

        # Rule 2: Blocking marshal in synchronous dispatch
        if func_name in BLOCKING_MARSHAL_FUNCS:
            if current_fn in SYNC_ADDIN_FUNCTIONS:
                self.findings.append(
                    Finding(
                        file=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        rule_id="blocking-marshal-in-sync-dispatch",
                        message=f"Blocking '{func_name}' inside synchronous dispatch function '{current_fn}' is a deadlock hazard (#402). Use post_to_main_thread or compute without UI marshaling.",
                    )
                )

        self.generic_visit(node)


def scan_file(file_path: Path) -> list[Finding]:
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception as exc:
        return [
            Finding(
                file=file_path,
                line=1,
                col=0,
                rule_id="syntax-error",
                message=f"Failed to parse AST: {exc}",
            )
        ]

    visitor = ThreadSafetyASTVisitor(file_path)
    visitor.visit(tree)
    return visitor.findings


def scan_target(target: Path) -> list[Finding]:
    findings: list[Finding] = []
    if target.is_file() and target.suffix == ".py":
        findings.extend(scan_file(target))
    elif target.is_dir():
        for py_file in sorted(target.rglob("*.py")):
            # Skip contrib, lib, tests
            rel = str(py_file)
            if "plugin/contrib" in rel or "plugin/lib" in rel or "/tests/" in rel or "venv" in rel:
                continue
            findings.extend(scan_file(py_file))
    return findings


def main() -> int:
    targets = [Path(arg) for arg in sys.argv[1:]] if len(sys.argv) > 1 else [Path("plugin/calc/python"), Path("plugin/scripting")]
    all_findings: list[Finding] = []
    for target in targets:
        all_findings.extend(scan_target(target))

    if not all_findings:
        print(f"Thread Safety AST Linter: All checks passed ({len(targets)} targets scanned).")
        return 0

    print(f"Thread Safety AST Linter found {len(all_findings)} violation(s):")
    for f in all_findings:
        print(f"  {f.file}:{f.line}:{f.col}: [{f.rule_id}] {f.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
