# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent Jedi environment helper for Monaco completions.

This runs entirely inside the pywebview Monaco editor child process in the user venv.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

# Try to import jedi dynamically. If missing, we degrade gracefully without autocomplete.
try:
    import jedi  # type: ignore
except ImportError:
    jedi = None


class JediSession:
    """Manages the persistent jedi.Environment for sub-10ms completions."""

    def __init__(self) -> None:
        self._env: Any = None
        if jedi is None:
            log.warning("jedi is not installed in the current Python environment")
            return

        try:
            # Create a persistent environment using sys.executable (our venv interpreter)
            # This is created once and reused for all keystrokes in this window session.
            self._env = jedi.create_environment(sys.executable)
            log.info("Successfully created persistent Jedi environment for %s", sys.executable)
        except Exception as e:
            log.warning("Could not create persistent Jedi environment, falling back to default: %s", e)

    def is_available(self) -> bool:
        """Return True if Jedi is imported successfully."""
        return jedi is not None

    def get_completions(self, code: str, line: int, column: int) -> dict[str, Any]:
        """Query Jedi for completions at the specified position.

        Jedi line is 1-based. Monaco column is 1-based, but Jedi column is 0-based,
        so we adjust column index by subtracting 1.
        """
        if not self.is_available() or jedi is None:
            return {"items": []}

        try:
            from plugin.scripting.venv_sandbox import apply_auto_imports

            # Prepend hidden auto-imports and adjust line number
            code, lines_added = apply_auto_imports(code)
            target_line = line + lines_added

            # Subtract 1 to convert from Monaco 1-indexed to Jedi 0-indexed column
            col_idx = max(0, column - 1)

            # Script parses the current editor content. Reuse persistent environment.
            script = jedi.Script(code, environment=self._env)
            completions = script.complete(target_line, col_idx)

            items = []
            for comp in completions:
                try:
                    doc = comp.docstring()
                except Exception:
                    doc = ""

                items.append({
                    "label": comp.name,
                    "kind": comp.type,  # Mapped to Monaco CompletionItemKind in JS
                    "insertText": comp.name,
                    "detail": comp.description or "",
                    "documentation": doc or "",
                })

            return {"items": items}
        except Exception:
            log.exception("Jedi completions failed")
            return {"items": []}
