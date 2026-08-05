"""Tests for optional PySpector wrapper (make pyspector; not a make test gate)."""

from __future__ import annotations

from scripts.run_pyspector import _DISABLED_RULE_IDS, _inject_disabled_rules


def test_inject_disabled_rules_adds_project_ids() -> None:
    sample = """
[defaults]
disabled_rule_ids = [
  "CACHE756",
]
"""
    out = _inject_disabled_rules(sample)
    assert '"PY101"' in out
    assert "WriterAgent project disable" in out
    # Idempotent
    assert _inject_disabled_rules(out) == out
    for rid in _DISABLED_RULE_IDS:
        assert f'"{rid}"' in out
    # Trusted GitHub audio_source.zip extract — accepted, disabled in wrapper.
    assert "ZIPSLIP001" in _DISABLED_RULE_IDS
