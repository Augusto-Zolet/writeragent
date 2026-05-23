#!/usr/bin/env python3
# WriterAgent — live formatter for CrossHair check / cover output
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Format CrossHair ``check`` and ``cover`` output for live terminal reading.

Pipe CrossHair ``-v`` through the filter (full module, no timeout)::

    crosshair check -v --report_all plugin/scripting/payload_codec.py 2>&1 \\
        | python scripts/crosshair_stream.py check

    crosshair cover -v plugin/scripting/payload_codec.py 2>&1 \\
        | python scripts/crosshair_stream.py cover

    make crosshair-check
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TextIO

CHECK_LINE = re.compile(
    r"^(?P<file>.+\.py):(?P<line>\d+): (?P<level>error|info|warning): (?P<msg>.*)$"
)
COVER_EXAMPLE = re.compile(r"^[A-Za-z_][\w.]*\(")
TRACE_LINE = re.compile(r"^(Traceback \(most recent call last\)|  File |TypeError:|ValueError:|IndexError:|KeyError:|AttributeError:)")
# CrossHair --verbose: "23222.229|    |analyze_function() Analyzing  foo"
VERBOSE_PREFIX = re.compile(r"^\d+\.\d+\|(?:\s*\|)*\s*")
VERBOSE_ANALYZE_FN = re.compile(r"analyze_function\(\)\s+Analyzing\s+(\S+)")
VERBOSE_ANALYZE_COND = re.compile(r"analyze\(\)\s+Analyzing (pre|post)condition:\s*(.+)", re.I)


@dataclass
class StreamStats:
    """Running counters while CrossHair streams."""

    confirmed: int = 0
    not_confirmed: int = 0
    unable: int = 0
    check_errors: int = 0
    progress: int = 0
    examples: int = 0
    explore: int = 0
    cover_errors: int = 0
    suppressed: int = 0
    lines: int = 0

    def summary(self, mode: str) -> str:
        if mode == "check":
            return (
                f"confirmed={self.confirmed} not_confirmed={self.not_confirmed} "
                f"unable={self.unable} errors={self.check_errors} progress={self.progress}"
            )
        if mode == "cover":
            return f"examples={self.examples} explore={self.explore} errors={self.cover_errors}"
        return (
            f"check(confirmed={self.confirmed} not_confirmed={self.not_confirmed} "
            f"unable={self.unable} errors={self.check_errors}) "
            f"cover(examples={self.examples} explore={self.explore} errors={self.cover_errors})"
        )


@dataclass
class ClassifiedLine:
    tag: str
    detail: str
    raw: str
    show_stats: bool = True


def _strip_crosshair_verbose(line: str) -> str:
    return VERBOSE_PREFIX.sub("", line.strip())


def _classify_crosshair_verbose(body: str) -> ClassifiedLine | None:
    """Pick milestone lines from ``crosshair check -v`` / ``cover -v`` stderr."""
    match = VERBOSE_ANALYZE_FN.search(body)
    if match:
        return ClassifiedLine("CHECK PROGRESS", f"analyzing {match.group(1)}", body, show_stats=False)

    match = VERBOSE_ANALYZE_COND.search(body)
    if match:
        kind = match.group(1).lower()
        expr = match.group(2).strip().strip('"')[:80]
        return ClassifiedLine("CHECK PROGRESS", f"{kind}: {expr}", body, show_stats=False)

    return None


def classify_line(line: str, mode: str) -> ClassifiedLine | None:
    """Classify one CrossHair or exploration line. Returns None to suppress noise."""
    stripped = line.strip()
    if not stripped:
        return None

    if mode in ("check", "auto"):
        match = CHECK_LINE.match(stripped)
        if match:
            loc = f"{Path(match.group('file')).name}:{match.group('line')}"
            msg = match.group("msg")
            if match.group("level") == "error":
                return ClassifiedLine("CHECK ERROR", f"{loc}  {msg}", stripped)
            if "Confirmed over all paths" in msg:
                return ClassifiedLine("CHECK CONFIRMED", loc, stripped)
            if "Not confirmed" in msg:
                return ClassifiedLine("CHECK NOT_CONFIRMED", loc, stripped)
            if "Unable to meet precondition" in msg:
                short = msg.split(" at ", 1)[0]
                return ClassifiedLine("CHECK UNABLE", f"{loc}  {short}", stripped)

        if VERBOSE_PREFIX.match(stripped):
            body = _strip_crosshair_verbose(stripped)
            if body.startswith("at (") or "choose_possible()" in body or "gen_args()" in body:
                return None
            if "pre_path_hook()" in body or "find_key_in_heap()" in body:
                return None
            verbose = _classify_crosshair_verbose(body)
            if verbose is not None:
                return verbose
            return None

    if mode in ("cover", "auto"):
        if COVER_EXAMPLE.match(stripped) and not stripped.startswith("payload_codec"):
            return ClassifiedLine("COVER EXAMPLE", stripped[:120], stripped)
        if stripped.startswith("payload_codec"):
            return ClassifiedLine("COVER EXPLORE", stripped[:120], stripped)
        if "Uneven row lengths" in stripped:
            return ClassifiedLine("COVER EXPLORE", stripped[:120], stripped)
        if TRACE_LINE.match(stripped):
            return ClassifiedLine("COVER FATAL", stripped[:120], stripped)

        if VERBOSE_PREFIX.match(stripped):
            body = _strip_crosshair_verbose(stripped)
            if "path_cover" in body or "analyze_function()" in body:
                match = VERBOSE_ANALYZE_FN.search(body)
                if match:
                    return ClassifiedLine("COVER PROGRESS", f"cover {match.group(1)}", body, show_stats=False)
            return None

    return None


def update_stats(stats: StreamStats, classified: ClassifiedLine) -> None:
    tag = classified.tag
    if tag == "CHECK CONFIRMED":
        stats.confirmed += 1
    elif tag == "CHECK NOT_CONFIRMED":
        stats.not_confirmed += 1
    elif tag == "CHECK UNABLE":
        stats.unable += 1
    elif tag == "CHECK ERROR":
        stats.check_errors += 1
    elif tag == "CHECK PROGRESS":
        stats.progress += 1
    elif tag == "COVER EXAMPLE":
        stats.examples += 1
    elif tag == "COVER EXPLORE":
        stats.explore += 1
    elif tag == "COVER FATAL":
        stats.cover_errors += 1
    elif tag in ("COVER PROGRESS",):
        stats.progress += 1


def effective_mode(tag: str, default_mode: str) -> str:
    if tag.startswith("CHECK"):
        return "check"
    if tag.startswith("COVER"):
        return "cover"
    return default_mode


def format_event(classified: ClassifiedLine, stats: StreamStats, mode: str) -> str:
    width = 22
    head = f"[{classified.tag:<{width}}] {classified.detail}"
    if not classified.show_stats:
        return head
    emode = effective_mode(classified.tag, mode)
    return f"{head}\n  -> {stats.summary(emode)}"


def stream_lines(
    lines: Iterator[str],
    *,
    mode: str,
    out: TextIO,
    raw: bool,
    quiet: bool,
) -> StreamStats:
    stats = StreamStats()
    seen_progress: set[str] = set()
    for line in lines:
        stats.lines += 1
        classified = classify_line(line, mode)
        if classified is None:
            stats.suppressed += 1
            if raw:
                out.write(f"[RAW] {line.rstrip()}\n")
                out.flush()
            continue
        if classified.tag.endswith("PROGRESS"):
            if classified.detail in seen_progress:
                stats.suppressed += 1
                continue
            seen_progress.add(classified.detail)
        update_stats(stats, classified)
        if quiet:
            if classified.tag.endswith("ERROR") or classified.tag == "COVER FATAL":
                out.write(format_event(classified, stats, mode) + "\n")
                out.flush()
            continue
        out.write(format_event(classified, stats, mode) + "\n")
        out.flush()
    return stats


def print_banner(stats: StreamStats, mode: str, exit_code: int, out: TextIO) -> None:
    label = mode.upper()
    failed = stats.check_errors + stats.cover_errors > 0 or exit_code == 1
    status = "FAIL" if failed else "DONE"
    out.write(
        f"\n=== CrossHair {label} {status} (exit {exit_code}) ===\n"
        f"  lines read: {stats.lines} (suppressed {stats.suppressed})\n"
        f"  {stats.summary(mode)}\n"
    )
    if mode in ("check", "auto"):
        out.write(
            "  check legend: PROGRESS=verbose milestone | CONFIRMED/NOT_CONFIRMED/UNABLE/ERROR=contract result\n"
        )
    if mode in ("cover", "auto"):
        out.write(
            "  cover legend: EXAMPLE=input that adds coverage | EXPLORE=path via log/exception\n"
        )
    out.flush()


def find_crosshair() -> str:
    path = shutil.which("crosshair")
    if path:
        return path
    venv = Path(".venv/bin/crosshair")
    if venv.exists():
        return str(venv)
    raise SystemExit("crosshair not found on PATH or in .venv/bin/")


def run_crosshair(command: str, crosshair_args: list[str], mode: str, raw: bool, quiet: bool) -> int:
    crosshair_path = find_crosshair()
    proc = subprocess.Popen(
        [crosshair_path, command, *crosshair_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    stats = stream_lines(proc.stdout, mode=mode, out=sys.stdout, raw=raw, quiet=quiet)
    exit_code = proc.wait()
    print_banner(stats, mode, exit_code, sys.stdout)
    return exit_code


def _pipe_mode(mode: str, raw: bool, quiet: bool) -> int:
    if sys.stdin.isatty():
        sys.stderr.write(
            "Reading CrossHair output from stdin. Example:\n"
            f"  crosshair {mode} -v --report_all TARGET 2>&1 | "
            f"python scripts/crosshair_stream.py {mode}\n"
        )
    stats = stream_lines(sys.stdin, mode=mode, out=sys.stdout, raw=raw, quiet=quiet)
    print_banner(stats, mode, 0, sys.stdout)
    return 0 if stats.check_errors + stats.cover_errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Filter CrossHair check/cover output (pipe crosshair -v through this script)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  crosshair check -v --report_all plugin/scripting/payload_codec.py 2>&1 \\\n"
            "      | python scripts/crosshair_stream.py check\n"
            "  make crosshair-check\n"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("check", "cover", "run"),
        help="check|cover = read stdin; run = spawn crosshair",
    )
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="With run: crosshair args after --")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only errors/fatals and final banner")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Also print suppressed lines as [RAW] (crosshair -v spam)",
    )

    args = parser.parse_args(argv)

    if args.command in ("check", "cover"):
        return _pipe_mode(args.command, args.raw, args.quiet)

    if args.command == "run":
        rest = args.rest
        if not rest:
            parser.error("run requires crosshair subcommand: run check ... or run cover ...")
        ch_cmd = rest[0]
        if ch_cmd not in ("check", "cover"):
            parser.error("run first arg must be check or cover")
        ch_args = rest[1:]
        if ch_args and ch_args[0] == "--":
            ch_args = ch_args[1:]
        return run_crosshair(ch_cmd, ch_args, ch_cmd, args.raw, args.quiet)

    # No command: stdin pipe, default check if piped
    if not sys.stdin.isatty():
        return _pipe_mode("check", args.raw, args.quiet)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
