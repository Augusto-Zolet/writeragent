# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from plugin.scripting.run_venv_code import (
    run_code_in_user_venv,
    scrub_subprocess_env,
    _parse_stdout_for_result,
)


def test_scrub_subprocess_env_drops_secrets():
    env = {"PATH": "/bin", "MY_API_KEY": "x", "HOME": "/home/u"}
    out = scrub_subprocess_env(env)
    assert "PATH" in out
    assert "HOME" in out
    assert "MY_API_KEY" not in out
    assert out.get("PYTHONIOENCODING") == "utf-8"


def test_parse_stdout_for_result():
    line = '__WRITERAGENT_VENV_RESULT__' + json.dumps({"a": 1})
    r, _ = _parse_stdout_for_result("noise\n" + line + "\n")
    assert r == {"a": 1}


def test_run_code_empty_config():
    ctx = MagicMock()
    with patch("plugin.scripting.run_venv_code.get_config_str", return_value=""):
        out = run_code_in_user_venv(ctx, "result = 1")
    assert out["status"] == "error"
    assert "No Python venv" in out["message"]


def test_run_code_whitespace_only():
    ctx = MagicMock()
    with patch("plugin.scripting.run_venv_code.get_config_str", return_value="/v"):
        out = run_code_in_user_venv(ctx, "   \n  ")
    assert out["status"] == "error"
    assert "No code" in out["message"]


def test_run_code_success():
    ctx = MagicMock()

    class Proc:
        returncode = 0
        stdout = "__WRITERAGENT_VENV_RESULT__42\n"
        stderr = ""

    with patch("plugin.scripting.run_venv_code.get_config_str", return_value="/fake/venv"):
        with patch("plugin.scripting.run_venv_code.resolve_venv_python", return_value="/fake/venv/bin/python"):
            with patch("plugin.scripting.run_venv_code.subprocess.run", return_value=Proc()) as run_mock:
                out = run_code_in_user_venv(ctx, "result = 40 + 2", timeout_sec=30)
    assert out["status"] == "ok"
    assert out["result"] == 42
    run_mock.assert_called_once()


def test_run_code_subprocess_timeout():
    ctx = MagicMock()
    import subprocess

    with patch("plugin.scripting.run_venv_code.get_config_str", return_value="/fake/venv"):
        with patch("plugin.scripting.run_venv_code.resolve_venv_python", return_value="/fake/venv/bin/python"):
            with patch(
                "plugin.scripting.run_venv_code.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
            ):
                out = run_code_in_user_venv(ctx, "result=1", timeout_sec=5)
    assert out["status"] == "error"
    assert "Timed out" in out["message"]
