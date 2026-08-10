#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Thin wrapper around scripts/fix_bare_underscore_throwaways.py
#
# Usage:
#   scripts/fix_bare_underscore_throwaways.sh --dry-run
#   scripts/fix_bare_underscore_throwaways.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/fix_bare_underscore_throwaways.py" "$@"
