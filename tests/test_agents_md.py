# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract tests for AGENTS.md size and split (Hermes 20k context cap)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_LEGALWORK_AGENTS = REPO_ROOT / "legalwork" / "AGENTS.md"
HERMES_CONTEXT_CAP = 20_000
AREA_FILE_CAP = 8_000

# Cross-cutting phrases that must remain in the *root* file (always injected).
ROOT_REQUIRED_PHRASES = (
    "self.ctx",
    "uno.getComponentContext()",
    "StreamQueueKind",
    "run_in_background",
    "guard_uno",
    "get_ctx()",
    "WriterAgentSmolModel",
    "tier=\"core\"",
    "Two products, one OXT",
    "text_helpers.py",
    "document_helpers",
    "python_config.py",
    "payload_codec.py",
    "plugin/chatbot/AGENTS.md",
    "plugin/writer/AGENTS.md",
    "plugin/calc/AGENTS.md",
    "plugin/scripting/AGENTS.md",
    "docs/repo-map.md",
)

AREA_FILES = (
    Path("plugin/chatbot/AGENTS.md"),
    Path("plugin/writer/AGENTS.md"),
    Path("plugin/calc/AGENTS.md"),
    Path("plugin/scripting/AGENTS.md"),
)

ORIENTATION = Path("docs/repo-map.md")

# Paths that used to live only in the root Key files table.
ORIENTATION_REQUIRED_PATHS = (
    "plugin/main.py",
    "plugin/main_core.py",
    "plugin/chatbot/panel.py",
    "plugin/chatbot/tool_loop.py",
    "plugin/chatbot/smol_agent.py",
    "plugin/framework/client/llm_client.py",
    "plugin/framework/tool.py",
    "plugin/doc/document_helpers.py",
    "plugin/doc/text_helpers.py",
    "plugin/framework/config.py",
    "plugin/writer/format.py",
    "plugin/framework/thread_guard.py",
    "plugin/testing_runner.py",
    "docs/chat-sidebar-implementation.md",
    "docs/framework-uno-thread-safety.md",
    "docs/scripting-librepy-split.md",
)


_ROOT_AGENTS = REPO_ROOT / "AGENTS.md"


@pytest.mark.skipif(not _ROOT_AGENTS.is_file(), reason="AGENTS.md not in stripped release tree")
def test_root_agents_md_under_hermes_char_cap() -> None:
    text = _ROOT_AGENTS.read_text(encoding="utf-8")
    assert len(text) <= HERMES_CONTEXT_CAP, (
        f"root AGENTS.md is {len(text)} chars; Hermes truncates above {HERMES_CONTEXT_CAP}"
    )


@pytest.mark.skipif(not _ROOT_AGENTS.is_file(), reason="AGENTS.md not in stripped release tree")
def test_root_agents_md_keeps_invariants() -> None:
    text = _ROOT_AGENTS.read_text(encoding="utf-8")
    missing = [p for p in ROOT_REQUIRED_PHRASES if p not in text]
    assert missing == [], f"root AGENTS.md missing required phrases: {missing}"


@pytest.mark.skipif(not _LEGALWORK_AGENTS.is_file(), reason="legalwork/AGENTS.md not present")
def test_legalwork_agents_md_untouched() -> None:
    text = _LEGALWORK_AGENTS.read_text(encoding="utf-8")
    assert "LegalWork" in text
    assert "WriterAgent" not in text


def test_area_agents_files_exist_and_are_small() -> None:
    for rel in AREA_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"missing {rel}"
        n = len(path.read_text(encoding="utf-8"))
        assert n <= AREA_FILE_CAP, f"{rel} is {n} chars (cap {AREA_FILE_CAP})"
        assert n > 200, f"{rel} looks empty"


@pytest.mark.skipif(
    not (REPO_ROOT / ORIENTATION).is_file(),
    reason="docs/repo-map.md not in stripped release tree",
)
def test_orientation_doc_has_entry_points() -> None:
    path = REPO_ROOT / ORIENTATION
    assert path.is_file(), f"missing {ORIENTATION}"
    text = path.read_text(encoding="utf-8")
    missing = [p for p in ORIENTATION_REQUIRED_PATHS if p not in text]
    assert missing == [], f"{ORIENTATION} missing paths: {missing}"
