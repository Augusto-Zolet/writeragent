# WriterAgent tests — crosshair_stream formatter
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from io import StringIO

from scripts.crosshair_stream import classify_line, stream_lines


def test_classify_check_confirmed() -> None:
    line = "/path/payload_codec.py:274: info: Confirmed over all paths."
    got = classify_line(line, "check")
    assert got is not None
    assert got.tag == "CHECK CONFIRMED"


def test_classify_check_error() -> None:
    line = "/path/payload_codec.py:483: error: IndexError when calling host_unpack_split_grid(...)"
    got = classify_line(line, "check")
    assert got is not None
    assert got.tag == "CHECK ERROR"


def test_classify_verbose_analyzing_function() -> None:
    line = "23222.229|    |analyze_function() Analyzing  host_pack_split_grid"
    got = classify_line(line, "check")
    assert got is not None
    assert got.tag == "CHECK PROGRESS"
    assert "host_pack_split_grid" in got.detail


def test_classify_verbose_choose_possible_suppressed() -> None:
    line = "23222.290|                  |choose_possible() SMT chose: Not(0 < grid_2_len_4)"
    assert classify_line(line, "check") is None


def test_classify_cover_example() -> None:
    got = classify_line("host_pack_split_grid([])", "cover")
    assert got is not None
    assert got.tag == "COVER EXAMPLE"


def test_stream_lines_check_summary() -> None:
    lines = [
        "plugin/scripting/payload_codec.py:274: info: Not confirmed.\n",
        "plugin/scripting/payload_codec.py:684: info: Confirmed over all paths.\n",
    ]
    buf = StringIO()
    stats = stream_lines(iter(lines), mode="check", out=buf, raw=False, quiet=False)
    assert stats.not_confirmed == 1
    assert stats.confirmed == 1
    out = buf.getvalue()
    assert "CHECK NOT_CONFIRMED" in out
    assert "CHECK CONFIRMED" in out
    assert "confirmed=1" in out


def test_stream_lines_verbose_milestone() -> None:
    lines = [
        "23222.229|    |analyze_function() Analyzing  host_pack_split_grid\n",
        "23222.251|    |analyze() Analyzing postcondition: \" isinstance(result, dict) \"\n",
    ]
    buf = StringIO()
    stats = stream_lines(iter(lines), mode="check", out=buf, raw=False, quiet=False)
    assert stats.progress == 2
    out = buf.getvalue()
    assert "CHECK PROGRESS" in out
    assert "choose_possible" not in out
