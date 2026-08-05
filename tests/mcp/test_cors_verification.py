# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""deal / CrossHair / Hypothesis verification for MCP CORS pure helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from plugin.mcp.cors import (
    is_safe_origin,
    normalize_cors_origin,
    normalize_origins_list,
    set_allow_private_origins,
    set_extra_allowed_origins,
)

CROSSHAIR_MODULE = "plugin/mcp/cors.py"
_CROSSHAIR_ERROR_RE = re.compile(r": error:")

_origin_candidates = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.just("localai.local"),
    st.sampled_from(
        [
            "https://localai.local",
            "https://localai.local/",
            "http://127.0.0.1:3000",
            "http://localhost",
            "https://evil.com",
            "ftp://x.com",
        ]
    ),
    st.text(max_size=40),
)


def _find_crosshair() -> str | None:
    crosshair_path = shutil.which("crosshair")
    if crosshair_path:
        return crosshair_path
    venv_bin_ch = Path(".venv/bin/crosshair")
    if venv_bin_ch.exists():
        return str(venv_bin_ch)
    return None


def setup_function() -> None:
    set_extra_allowed_origins([])
    set_allow_private_origins(True)


def teardown_function() -> None:
    set_extra_allowed_origins([])
    set_allow_private_origins(True)


@given(value=_origin_candidates)
@settings(max_examples=80)
def test_hypothesis_normalize_cors_origin_shape(value) -> None:
    result = normalize_cors_origin(value)
    if result is None:
        return
    assert result.startswith(("http://", "https://", "HTTP://", "HTTPS://")) or result.lower().startswith(("http://", "https://"))
    assert not result.endswith("/")


@given(
    value=st.one_of(
        st.none(),
        st.just("https://a.com/"),
        st.lists(st.sampled_from(["https://a.com", "https://a.com/", "https://b.com", 1, None]), max_size=5),
        st.just(123),
    )
)
@settings(max_examples=60)
def test_hypothesis_normalize_origins_list_idempotent(value) -> None:
    once = normalize_origins_list(value)
    twice = normalize_origins_list(once)
    assert twice == once
    assert len(once) == len(set(once))


def test_localhost_safe_origin() -> None:
    assert is_safe_origin("http://localhost:3000")
    assert is_safe_origin("http://127.0.0.1")
    assert is_safe_origin("http://[::1]")


@pytest.mark.slow
def test_crosshair_cors_if_available() -> None:
    crosshair_path = _find_crosshair()
    if not crosshair_path:
        pytest.skip("CrossHair concolic execution engine is not installed.")
    result = subprocess.run(
        [crosshair_path, "check", "-v", "--report_all", CROSSHAIR_MODULE],
        capture_output=True,
        text=True,
        timeout=600,
    )
    combined = f"{result.stdout}\n{result.stderr}".strip()
    print(f"CrossHair output:\n{combined}")
    errors = [line for line in combined.splitlines() if _CROSSHAIR_ERROR_RE.search(line)]
    assert not errors, "CrossHair counterexamples found:\n" + "\n".join(errors)
    if result.returncode == 2:
        pytest.fail(f"CrossHair internal error (exit 2):\n{combined}")
