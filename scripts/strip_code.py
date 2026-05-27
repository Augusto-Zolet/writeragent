#!/usr/bin/env python3
# WriterAgent — AST-based grammar_obs stripping tool
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""AST-based utility to strip ``grammar_obs(...)`` call sites from production bundles.

Only removes standalone expression-statement calls to ``grammar_obs`` or ``_grammar_obs``.
Imports, re-exports, the ``grammar_obs.py`` module, and ``emit_grammar_status`` are left intact.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

GRAMMAR_OBS_CALL_NAMES: frozenset[str] = frozenset({"grammar_obs", "_grammar_obs"})

EXCLUDED_STRIP_PATTERNS: list[str] = [
    "plugin/testing_runner.py",
    "plugin/tests/",
    "tests/",
]


def should_skip_strip(rel_path: str) -> bool:
    """Determine if a project-relative Python file should be skipped during stripping."""
    for pattern in EXCLUDED_STRIP_PATTERNS:
        if pattern.endswith("/"):
            if rel_path.startswith(pattern):
                return True
        elif rel_path == pattern:
            return True
    return False


def _is_grammar_obs_call(node: ast.Expr) -> bool:
    """True if ``node`` is an expression-statement call to grammar_obs / _grammar_obs."""
    if not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Name) and func.id in GRAMMAR_OBS_CALL_NAMES


def strip_grammar_obs_calls(bundle_path: str, dry_run: bool = False) -> None:
    """Remove ``grammar_obs(...)`` / ``_grammar_obs(...)`` expression statements from Python files.

    Uses AST line ranges (including multi-line calls). Inserts ``pass`` when stripping would
    leave an otherwise empty block.
    """
    action = "Dry run: would strip" if dry_run else "Stripping"
    print(f"  {action} grammar_obs calls from {bundle_path} using AST...")

    for root, _, filenames in os.walk(bundle_path):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            rel_path = os.path.relpath(path, bundle_path).replace(os.sep, "/")
            if should_skip_strip(rel_path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    lines = content.splitlines(keepends=True)

                tree = ast.parse(content)

                parent_map: dict[ast.AST, ast.AST] = {}
                for node in ast.walk(tree):
                    for child in ast.iter_child_nodes(node):
                        parent_map[child] = node

                nodes_to_remove: list[ast.Expr] = []

                class FindVisitor(ast.NodeVisitor):
                    def visit_Expr(self, node: ast.Expr) -> None:
                        if _is_grammar_obs_call(node):
                            nodes_to_remove.append(node)
                        self.generic_visit(node)

                FindVisitor().visit(tree)
                if not nodes_to_remove:
                    continue

                replacements: dict[int, str] = {}
                to_delete: set[int] = set()

                def get_container(node: ast.AST) -> list[ast.stmt] | None:
                    parent = parent_map.get(node)
                    if not parent:
                        return None
                    for attr in ("body", "orelse", "finalbody"):
                        if hasattr(parent, attr):
                            container = getattr(parent, attr)
                            if isinstance(container, list) and node in container:
                                return container
                    if isinstance(parent, ast.Try):
                        for handler in parent.handlers:
                            if node in handler.body:
                                return handler.body
                    return None

                for node in nodes_to_remove:
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", None) or start_line
                    first_idx = start_line - 1
                    last_idx = end_line - 1
                    original_line = lines[first_idx]
                    indent = original_line[: len(original_line) - len(original_line.lstrip())]

                    if dry_run:
                        rel_p = os.path.relpath(path, bundle_path)
                        snippet = original_line.strip()
                        if end_line > start_line:
                            snippet += f" ... (spans {end_line - start_line + 1} lines)"
                        print(f"    [DryRun] {rel_p}: L{start_line}-{end_line}: {snippet}")
                        continue

                    container = get_container(node)
                    needs_pass = False
                    if container and not isinstance(parent_map.get(node), ast.Module):
                        remaining = [s for s in container if s not in nodes_to_remove]
                        if not remaining:
                            first_removed = next(s for s in container if s in nodes_to_remove)
                            if node is first_removed:
                                needs_pass = True

                    if needs_pass:
                        replacements[first_idx] = f"{indent}pass  # stripped grammar_obs\n"
                        for idx in range(first_idx + 1, last_idx + 1):
                            to_delete.add(idx)
                    else:
                        for idx in range(first_idx, last_idx + 1):
                            to_delete.add(idx)

                if dry_run:
                    continue

                new_lines: list[str] = []
                for i, line in enumerate(lines):
                    if i in to_delete and i not in replacements:
                        continue
                    if i in replacements:
                        new_lines.append(replacements[i])
                    else:
                        new_lines.append(line)

                with open(path, "w", encoding="utf-8") as f:
                    f.write("".join(new_lines))

            except Exception as e:
                if "match" not in str(e):
                    print(f"    SKIPPING {fn}: {e}")

    print("  Done: Stripped grammar_obs calls from bundle.")


def strip_production_code(bundle_path: str, dry_run: bool = False) -> None:
    """Release-bundle entry point: strip ``grammar_obs`` call sites only."""
    strip_grammar_obs_calls(bundle_path, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Strip grammar_obs(...) calls from python files in a directory.")
    parser.add_argument("bundle_path", help="Path to the directory containing python files to strip")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be stripped without deleting")
    args = parser.parse_args()

    if not os.path.isdir(args.bundle_path):
        print(f"Error: {args.bundle_path} is not a valid directory.", file=sys.stderr)
        return 1

    strip_grammar_obs_calls(args.bundle_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
