# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Static AST policy checks for LocalPythonExecutor (no execution)."""

from __future__ import annotations

import ast

from plugin.contrib.smolagents.local_python_executor import check_import_authorized

# Statement/expression forms the interpreter refuses outright (see evaluate_ast else branch).
_FORBIDDEN_NODE_TYPES: tuple[type[ast.AST], ...] = (
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Global,
    ast.Nonlocal,
    ast.NamedExpr,
)
if hasattr(ast, "Match"):
    _FORBIDDEN_NODE_TYPES = _FORBIDDEN_NODE_TYPES + (ast.Match,)  # type: ignore[attr-defined]
if hasattr(ast, "MatchStar"):
    _FORBIDDEN_NODE_TYPES = _FORBIDDEN_NODE_TYPES + (ast.MatchStar,)  # type: ignore[attr-defined]


def validate_sandbox_ast(module: ast.Module, authorized_imports: list[str]) -> str | None:
    """Return an error message if *module* violates sandbox policy, else ``None``."""
    for node in ast.walk(module):
        if isinstance(node, _FORBIDDEN_NODE_TYPES):
            return f"{node.__class__.__name__} is not supported."
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not check_import_authorized(alias.name, authorized_imports):
                    return (
                        f"Import of {alias.name} is not allowed. "
                        f"Authorized imports are: {str(authorized_imports)}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if not check_import_authorized(module_name, authorized_imports):
                return (
                    f"Import from {module_name} is not allowed. "
                    f"Authorized imports are: {str(authorized_imports)}"
                )
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return f"Forbidden access to dunder attribute: {node.attr}"
    return None
