#!/usr/bin/env python3
"""Convert Opengrep / Semgrep YAML rule files to PySpector TOML rule format.

Allows PySpector to evaluate custom project rules (such as UNO thread safety and
security rules in tests/semgrep/) across python files and modules.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMGREP_DIR = REPO_ROOT / "tests" / "semgrep"


def _clean_pattern(pattern_str: str) -> str:
    """Convert simple Opengrep patterns/calls to regex patterns for PySpector."""
    p = pattern_str.strip()
    # If pattern is a simple function call like "tempfile.mktemp(...)" or "get_ctx(...)"
    m = re.match(r"^([a-zA-Z0-9_\.]+)\s*\(\s*\.\.\.\s*\)$", p)
    if m:
        fn_name = re.escape(m.group(1))
        return rf"\b{fn_name}\s*\("

    # Fallback: escape dots and convert wildcard ellipses to regex
    res = re.escape(p).replace(r"\.\.\.", r".*")
    return res


def extract_regex_patterns(rule_def: dict[str, Any]) -> list[str]:
    """Extract regex pattern strings from Opengrep rule definition."""
    patterns: list[str] = []
    rule_id = str(rule_def.get("id", "")).lower()

    if "raw-uno-thread-ban" in rule_id or "raw_uno_thread_ban" in rule_id:
        patterns.append(r"\b(threading\.(Thread|Timer)|Thread|Timer)\s*\(")
        return patterns

    if "writeragent-no-tempfile-mktemp" in rule_id or "writeragent_no_tempfile_mktemp" in rule_id:
        patterns.append(r"\btempfile\.mktemp\s*\(")
        return patterns

    if "pattern" in rule_def:
        patterns.append(_clean_pattern(str(rule_def["pattern"])))

    if "pattern-either" in rule_def and isinstance(rule_def["pattern-either"], list):
        sub_pats: list[str] = []
        for item in rule_def["pattern-either"]:
            if isinstance(item, dict) and "pattern" in item:
                sub_pats.append(_clean_pattern(str(item["pattern"])))
            elif isinstance(item, str):
                sub_pats.append(_clean_pattern(item))
        if sub_pats:
            patterns.append("|".join(f"({p})" for p in sub_pats))

    if "pattern-sinks" in rule_def and isinstance(rule_def["pattern-sinks"], list):
        sink_pats: list[str] = []
        for sink in rule_def["pattern-sinks"]:
            if isinstance(sink, dict) and "pattern-either" in sink:
                for item in sink["pattern-either"]:
                    if isinstance(item, dict) and "pattern" in item:
                        sink_pats.append(_clean_pattern(str(item["pattern"])))
            elif isinstance(sink, dict) and "pattern" in sink:
                sink_pats.append(_clean_pattern(str(sink["pattern"])))
        if sink_pats:
            patterns.append("|".join(f"({p})" for p in sink_pats))

    return patterns


def convert_semgrep_yaml_to_pyspector_toml(yaml_path: Path) -> str:
    """Convert an Opengrep YAML rule file to PySpector TOML rules snippet."""
    if yaml is None or not yaml_path.is_file():
        return ""

    content = yaml_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(content)
    except Exception:
        return ""

    if not isinstance(data, dict) or "rules" not in data or not isinstance(data["rules"], list):
        return ""

    toml_blocks: list[str] = []

    for r in data["rules"]:
        if not isinstance(r, dict):
            continue

        raw_id = str(r.get("id", "SEMGREP_RULE"))
        rule_id = raw_id.upper().replace("-", "_")

        # Skip complex taint-mode rules that require intrafile/interfile call graph taint analysis
        if r.get("mode") == "taint" and "uno-off-main-thread" in raw_id.lower():
            continue
        msg = str(r.get("message", "")).replace("\n", " ").strip()
        sev_str = str(r.get("severity", "WARNING")).upper()
        severity_map = {"ERROR": "High", "WARNING": "Medium", "INFO": "Low"}
        severity = severity_map.get(sev_str, "Medium")

        pats = extract_regex_patterns(r)
        if not pats:
            continue

        combined_pattern = pats[0] if len(pats) == 1 else "|".join(f"({p})" for p in pats)

        exclude_paths = []
        if "paths" in r and isinstance(r["paths"], dict) and "exclude" in r["paths"]:
            for x in r["paths"]["exclude"]:
                clean_x = str(x).replace("**/", "").strip()
                if clean_x:
                    exclude_paths.append(f"*{clean_x}" if not clean_x.startswith("*") else clean_x)

        exclude_pat_str = ",".join(exclude_paths) if exclude_paths else ""
        safe_pattern = combined_pattern.replace("\\", "\\\\").replace('"', '\\"')
        safe_msg = msg.replace('"', '\\"')
        safe_exclude = exclude_pat_str.replace('"', '\\"')

        toml_rule = (
            f"[[rule]]\n"
            f'id = "{rule_id}"\n'
            f'description = "{safe_msg}"\n'
            f'severity = "{severity}"\n'
            f'confidence = "High"\n'
            f'remediation = "{safe_msg}"\n'
            f'pattern = "{safe_pattern}"\n'
            f'file_pattern = "*.py"\n'
            f'exclude_pattern = ".*#.*nosemgrep.*"\n'
        )

        if safe_exclude:
            toml_rule += f'exclude_file_pattern = "{safe_exclude}"\n'

        toml_blocks.append(toml_rule)

    return "\n".join(toml_blocks)


def get_converted_semgrep_rules(rule_files: Sequence[Path] | None = None) -> str:
    """Load and convert all project semgrep YAML rules to PySpector TOML format."""
    if rule_files is None:
        rule_files = [
            SEMGREP_DIR / "uno_thread_safety.yml",
            SEMGREP_DIR / "writeragent_security.yml",
        ]

    blocks = []
    for path in rule_files:
        converted = convert_semgrep_yaml_to_pyspector_toml(path)
        if converted:
            blocks.append(converted)

    return "\n\n".join(blocks)
