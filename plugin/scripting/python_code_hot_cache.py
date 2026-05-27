# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""In-memory hot cache: parsed AST + static sandbox validation for unchanged code."""

from __future__ import annotations

import ast
import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass

from plugin.scripting.sandbox_static_validate import validate_sandbox_ast

_DEFAULT_MAX_ENTRIES = 4096


@dataclass(frozen=True, slots=True)
class HotEntry:
    """Cached parse + static validation for one code + import-policy key."""

    module: ast.Module | None
    error: str | None


_lock = threading.Lock()
_cache: OrderedDict[str, HotEntry] = OrderedDict()
_max_entries = _DEFAULT_MAX_ENTRIES


def _imports_fingerprint(authorized_imports: list[str]) -> str:
    return "\n".join(sorted(set(authorized_imports)))


def _cache_key(code: str, authorized_imports: list[str]) -> str:
    material = code + "\0" + _imports_fingerprint(authorized_imports)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _format_syntax_error(exc: SyntaxError) -> str:
    text = exc.text or ""
    return (
        f"Code parsing failed on line {exc.lineno} due to: {type(exc).__name__}: {str(exc)}\n"
        f"{text}"
        f"{' ' * (exc.offset or 0)}^"
    )


def _build_entry(code: str, authorized_imports: list[str]) -> HotEntry:
    try:
        module = ast.parse(code)
    except SyntaxError as exc:
        return HotEntry(module=None, error=_format_syntax_error(exc))
    validation_error = validate_sandbox_ast(module, authorized_imports)
    return HotEntry(module=module, error=validation_error)


def get_hot_entry(code: str, authorized_imports: list[str]) -> HotEntry:
    """Return cached or freshly built parse + static validation for *code*."""
    key = _cache_key(code, authorized_imports)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    entry = _build_entry(code, authorized_imports)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        _cache[key] = entry
        if len(_cache) > _max_entries:
            _cache.popitem(last=False)
    return entry


def clear_python_code_hot_cache() -> None:
    """Clear the hot cache (tests)."""
    with _lock:
        _cache.clear()
