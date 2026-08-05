#!/usr/bin/env python3
"""Run PySpector on plugin/ with project FP rules disabled.

Used by ``make pyspector`` / ``make pyspector-report``. Not part of make test.
Disables rules reviewed as false positives or accepted known risks for WriterAgent.
"""

from __future__ import annotations

import sys

# Rule IDs reviewed as false positives or accepted known risks for WriterAgent.
_DISABLED_RULE_IDS = (
    "PY101",  # Tool.execute / chart helpers mistaken for SQL cursor.execute
    "PATH813",  # controlled cache/gallery mkdir/unlink/read
    "IMPORT825",  # fixed UNO / sys __import__ strings
    "GETATTR828",  # log_level allowlisted in resolve_log_level
    "REGEX870",  # short Calc sheet-ref regex; not attacker-controlled megabytes
    "PY002",  # pickle on trusted host↔venv IPC pipe (# nosec)
    "TLS001",  # optional verify-off for local/self-signed LLM endpoints
    "PY102",  # pdfinfo argv-list; local fidelity helper
    "ZIPSLIP001",  # audio_source.zip from fixed GitHub contrib URL only
)


def _inject_disabled_rules(rules_toml: str) -> str:
    """Extend the built-in [defaults].disabled_rule_ids list."""
    marker = "disabled_rule_ids = ["
    idx = rules_toml.find(marker)
    if idx < 0:
        extra = ",\n".join(f'  "{rid}",' for rid in _DISABLED_RULE_IDS)
        return rules_toml + f"\n[defaults]\ndisabled_rule_ids = [\n{extra}\n]\n"
    # Idempotent: already injected for this project.
    window = rules_toml[idx : idx + 1200]
    if '"PY101"' in window and "WriterAgent project disable" in window:
        return rules_toml
    insert_at = idx + len(marker)
    lines = "".join(f'\n  "{rid}",  # WriterAgent project disable' for rid in _DISABLED_RULE_IDS)
    return rules_toml[:insert_at] + lines + rules_toml[insert_at:]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    from pyspector import cli as pyspector_cli
    from pyspector import config as pyspector_config

    original = pyspector_config.get_default_rules

    def patched_get_default_rules(ai_scan: bool = False) -> str:
        return _inject_disabled_rules(original(ai_scan))

    pyspector_config.get_default_rules = patched_get_default_rules
    pyspector_cli.get_default_rules = patched_get_default_rules

    if not argv:
        argv = ["scan", "plugin", "--ai", "-c", "pyspector.toml", "--msg=False"]

    try:
        pyspector_cli.cli.main(args=argv, prog_name="pyspector")
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else (1 if code else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
