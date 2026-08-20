# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""deal / Hypothesis / CrossHair verification for stream_normalizer pure helpers."""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from pathlib import Path

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from plugin.framework.client.stream_normalizer import (
    ThinkTagStreamSplitter,
    _merge_reasoning_details,
    _normalize_delta,
    _normalize_stream_delta,
    _thinking_text_from_delta,
    accumulate_streaming_thinking,
    extract_reasoning_replay_from_response,
    new_streaming_thinking_meta,
    strip_think_tags,
)
from tests.vhs_budget import vhs_max_examples

_CROSSHAIR_ERROR_RE = re.compile(r": error:")
_CROSSHAIR_TARGETS = (
    "plugin.framework.client.stream_normalizer._merge_reasoning_details",
    "plugin.framework.client.stream_normalizer._thinking_text_from_delta",
    # _normalize_stream_delta is # crosshair: off (Literal TypedDict heap crash); covered by unit tests.
)


def _find_crosshair() -> str | None:
    crosshair_path = shutil.which("crosshair")
    if crosshair_path:
        return crosshair_path
    venv_bin_ch = Path(".venv/bin/crosshair")
    if venv_bin_ch.exists():
        return str(venv_bin_ch)
    return None


@given(parts=st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=5))
@settings(max_examples=vhs_max_examples(40, 400), deadline=None)
def test_hypothesis_thinking_text_prefers_reasoning_content(parts: list[str]) -> None:
    """reasoning_content wins over other string thinking fields."""
    delta = {
        "reasoning_content": "".join(parts),
        "reasoning": "ignored",
        "thinking": "also-ignored",
    }
    assert _thinking_text_from_delta(delta) == "".join(parts)


@given(
    chunks=st.lists(
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=10),
        min_size=1,
        max_size=6,
    )
)
@settings(max_examples=vhs_max_examples(50, 500), deadline=None)
def test_hypothesis_accumulate_thinking_concat(chunks: list[str]) -> None:
    text_parts: list[str] = []
    meta = new_streaming_thinking_meta()
    for chunk in chunks:
        accumulate_streaming_thinking(text_parts, meta, {"reasoning": chunk})
    assert "".join(text_parts) == "".join(c for c in chunks if c)
    assert meta["source"] in (None, "reasoning")


@given(
    a=st.text(max_size=20),
    b=st.text(max_size=20),
    idx=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=vhs_max_examples(40, 400), deadline=None)
def test_hypothesis_merge_reasoning_details_chunked_equals_full(a: str, b: str, idx: int) -> None:
    chunked = _merge_reasoning_details(
        [
            {"type": "reasoning.text", "text": a, "index": idx},
            {"type": "reasoning.text", "text": b, "index": idx},
        ]
    )
    full = _merge_reasoning_details([{"type": "reasoning.text", "text": a + b, "index": idx}])
    assert chunked == full
    assert len(chunked) == 1
    assert chunked[0]["text"] == a + b


def test_normalize_stream_delta_unwraps_choices() -> None:
    bare = {"reasoning": "x"}
    wrapped = {"choices": [{"delta": bare}]}
    assert _normalize_stream_delta(wrapped) == bare
    assert _normalize_stream_delta(bare) == bare
    assert _normalize_stream_delta("not-a-dict") == {}


def test_accumulate_streaming_thinking_rejects_invalid_source() -> None:
    """CrossHair found ensure false for meta source=''; pre + body guard reject/clear it.

    With deal installed (dev venv), pre raises; under LibreOffice deal_shim the body
    clears source to None. Either way ensure-equivalent invariant holds.
    """
    text_parts: list[str] = []
    meta_bad: dict[str, object] = {"source": ""}
    try:
        accumulate_streaming_thinking(text_parts, meta_bad, {})
    except deal.PreContractError:
        pass
    else:
        assert meta_bad.get("source") is None
    meta = new_streaming_thinking_meta()
    accumulate_streaming_thinking(text_parts, meta, {"reasoning": "hello"})
    assert text_parts == ["hello"]
    assert meta["source"] == "reasoning"


def test_normalize_delta_repairs_mistral_nulls() -> None:
    delta = {
        "role": None,
        "tool_calls": [{"type": None, "function": {"name": "f", "arguments": None}}],
    }
    _normalize_delta(delta)
    assert delta["role"] == "assistant"
    assert delta["tool_calls"][0]["type"] == "function"
    assert delta["tool_calls"][0]["function"]["arguments"] == ""


def test_normalize_delta_ignores_non_list_tool_calls() -> None:
    """CrossHair found TypeError iterating tool_calls=2 (truthy non-list)."""
    delta = {"role": None, "tool_calls": 2}
    _normalize_delta(delta)
    assert delta["role"] == "assistant"
    assert delta["tool_calls"] == 2


def test_merge_reasoning_details_skips_non_dicts() -> None:
    merged = _merge_reasoning_details(
        [None, "x", {"type": "reasoning.text", "text": "a", "index": 0}, {"type": "reasoning.text", "text": "b", "index": 0}]
    )
    assert merged == [{"type": "reasoning.text", "text": "ab", "index": 0}]


def test_merge_reasoning_details_skips_dict_subclass_deepcopy_bomb() -> None:
    """CrossHair AttrDict is isinstance(dict) but deepcopy KeyErrors; plain-dict guard skips it."""

    class _DeepcopyBomb(dict):
        def __deepcopy__(self, memo: object) -> dict:
            raise KeyError("__deepcopy__")

    bomb = _DeepcopyBomb({"type": "reasoning.text", "text": "nope", "index": 0})
    plain = {"type": "reasoning.text", "text": "a", "index": 0}
    merged = _merge_reasoning_details([bomb, plain, {"type": "reasoning.text", "text": "b", "index": 0}])
    assert merged == [{"type": "reasoning.text", "text": "ab", "index": 0}]
    assert bomb not in merged


def test_merge_does_not_mutate_input_entries() -> None:
    original = [{"type": "reasoning.text", "text": "a", "index": 0}]
    snapshot = copy.deepcopy(original)
    _merge_reasoning_details(original + [{"type": "reasoning.text", "text": "b", "index": 0}])
    assert original == snapshot


def _joined_splitter(chunks: list[str]) -> tuple[str, str | None]:
    """Feed chunks through ThinkTagStreamSplitter.

    Thinking fragments of one ``<think>`` block are concatenated (not joined with
    newlines — that join is only for *separate* blocks in strip_think_tags).
    """
    splitter = ThinkTagStreamSplitter()
    content: list[str] = []
    thinking: list[str] = []
    for ch in chunks:
        for is_t, piece in splitter.feed(ch):
            (thinking if is_t else content).append(piece)
    for is_t, piece in splitter.flush():
        (thinking if is_t else content).append(piece)
    extracted = "".join(thinking).strip() or None
    return "".join(content).strip(), extracted


@given(
    body=st.text(max_size=40).filter(lambda t: "<think>" not in t and "</think>" not in t),
    thought=st.text(max_size=40).filter(lambda t: "<think>" not in t and "</think>" not in t),
    cuts=st.lists(st.integers(min_value=0, max_value=80), min_size=0, max_size=6),
)
@settings(max_examples=vhs_max_examples(40, 400), deadline=None)
def test_hypothesis_think_tag_chunks_match_strip(body: str, thought: str, cuts: list[int]) -> None:
    full = f"{body}<think>{thought}</think>{body}"
    pts = sorted({0, len(full), *(min(max(0, c), len(full)) for c in cuts)})
    chunks = [full[a:b] for a, b in zip(pts, pts[1:]) if a < b]
    content, thinking = _joined_splitter(chunks)
    clean, extracted = strip_think_tags(full)
    assert content == clean
    # strip_think_tags yields "" when the only blocks were empty; splitter yields None.
    assert (thinking or None) == (extracted or None)


def test_strip_think_tags_removes_complete_blocks() -> None:
    clean, thinking = strip_think_tags("a<think>x</think>b<think>y</think>c")
    assert "<think>" not in clean
    assert thinking == "x\n\ny"


_REPLAY_KEYS = frozenset({"reasoning", "reasoning_content", "reasoning_details"})


@given(text=st.text(max_size=30), snap_reason=st.text(max_size=20))
@settings(max_examples=vhs_max_examples(30, 300), deadline=None)
def test_hypothesis_streaming_text_ignores_snapshot(text: str, snap_reason: str) -> None:
    meta = new_streaming_thinking_meta()
    meta["source"] = "reasoning"
    replay = extract_reasoning_replay_from_response(
        message_snapshot={"reasoning": snap_reason},
        streaming_text=text,
        streaming_meta=meta,
    )
    assert set(replay.keys()) <= _REPLAY_KEYS
    if text:
        assert replay == {"reasoning": text}
    else:
        assert replay == {}


def test_replay_keys_subset_on_details_path() -> None:
    replay = extract_reasoning_replay_from_response(
        sync_message={"reasoning_details": [{"type": "reasoning.text", "text": "a", "index": 0}]}
    )
    assert set(replay.keys()) <= _REPLAY_KEYS
    assert isinstance(replay["reasoning_details"], list)


@pytest.mark.slow
@pytest.mark.parametrize("target", _CROSSHAIR_TARGETS)
def test_crosshair_stream_normalizer_fqn_if_available(target: str) -> None:
    crosshair_path = _find_crosshair()
    if not crosshair_path:
        pytest.skip("CrossHair concolic execution engine is not installed.")
    result = subprocess.run(
        [crosshair_path, "check", "-v", "--report_all", target],
        capture_output=True,
        text=True,
        timeout=300,
    )
    combined = f"{result.stdout}\n{result.stderr}".strip()
    print(f"CrossHair output ({target}):\n{combined}")
    errors = [line for line in combined.splitlines() if _CROSSHAIR_ERROR_RE.search(line)]
    assert not errors, "CrossHair counterexamples found:\n" + "\n".join(errors)
    if result.returncode == 2:
        pytest.fail(f"CrossHair internal error (exit 2):\n{combined}")
