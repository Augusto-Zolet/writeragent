# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural tests for Calc Python accelerators in both OXTs."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_OOR_NS = "http://openoffice.org/2001/registry"
_OOR_NAME = "{%s}name" % _OOR_NS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manifest_registry import generate_accelerators_xcu  # noqa: E402

_CALC_SVC = "com.sun.star.sheet.SpreadsheetDocument"
_LIBREPY_XCU = _REPO_ROOT / "extension-core" / "Accelerators.xcu"
_WRITERAGENT_XCU = _REPO_ROOT / "extension" / "Accelerators.xcu"


def _commands_by_key(xcu: Path, module_svc: str) -> dict[str, str]:
    root = ET.parse(xcu).getroot()
    out: dict[str, str] = {}
    for modules in root.iter("node"):
        if modules.get(_OOR_NAME) != "Modules":
            continue
        for svc in modules.findall("node"):
            if svc.get(_OOR_NAME) != module_svc:
                continue
            for key_node in svc.findall("node"):
                key = key_node.get(_OOR_NAME)
                if not key:
                    continue
                for prop in key_node.findall("prop"):
                    if prop.get(_OOR_NAME) == "Command":
                        value = prop.find("value")
                        if value is not None and value.text:
                            out[key] = value.text.strip()
    return out


def test_librepy_accelerators_use_librepy_protocol():
    cmds = _commands_by_key(_LIBREPY_XCU, _CALC_SVC)
    assert cmds["F9_SHIFT_MOD1_MOD2"] == "org.extension.librepy:scripting.reset_python_session"
    assert cmds["P_SHIFT_MOD1_MOD2"] == "org.extension.librepy:scripting.edit_python_cell"


def test_librepy_manifest_registers_accelerators():
    text = (_REPO_ROOT / "extension-core" / "META-INF" / "manifest.xml").read_text(encoding="utf-8")
    assert 'manifest:full-path="Accelerators.xcu"' in text


def test_writeragent_accelerators_keep_chat_and_add_python():
    cmds = _commands_by_key(_WRITERAGENT_XCU, _CALC_SVC)
    assert cmds["Q_MOD1"].endswith("ExtendSelection")
    assert cmds["F9_SHIFT_MOD1_MOD2"] == "org.extension.writeragent:scripting.reset_python_session"
    assert cmds["P_SHIFT_MOD1_MOD2"] == "org.extension.writeragent:scripting.edit_python_cell"


def test_generate_accelerators_xcu_emits_writeragent_python_urls(tmp_path):
    out = tmp_path / "Accelerators.xcu"
    modules = [
        {
            "name": "scripting",
            "shortcuts": {
                "reset_python_session": {"key": "F9_SHIFT_MOD1_MOD2", "context": ["calc"]},
                "edit_python_cell": {"key": "P_SHIFT_MOD1_MOD2", "context": ["calc"]},
            },
        }
    ]
    generate_accelerators_xcu(modules, str(out))
    cmds = _commands_by_key(out, _CALC_SVC)
    assert cmds["F9_SHIFT_MOD1_MOD2"] == "org.extension.writeragent:scripting.reset_python_session"
    assert cmds["P_SHIFT_MOD1_MOD2"] == "org.extension.writeragent:scripting.edit_python_cell"
