#!/usr/bin/env bash
# Rebuild Calc add-in typelibraries from IDL (one .rdb per interface; unoidl-write
# only retains the last IDL when several are passed to a single output file).
# Requires LibreOffice SDK (libreoffice-fresh-sdk): unoidl-write
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IDL_PYTHON="$ROOT/extension/idl/XPythonFunction.idl"
IDL_PROMPT="$ROOT/extension/idl/XPromptFunction.idl"
RDB_PYTHON="$ROOT/extension/XPythonFunction.rdb"
RDB_PROMPT="$ROOT/extension/XPromptFunction.rdb"
SDK_HOME="${OO_SDK_HOME:-/usr/lib/libreoffice/sdk}"
UNOIDLWRITE="${SDK_HOME}/bin/unoidl-write"

if [[ ! -x "$UNOIDLWRITE" ]]; then
  echo "error: unoidl-write not found at $UNOIDLWRITE (install libreoffice-fresh-sdk)." >&2
  exit 1
fi

# Paths from sdk/settings/std.mk (Linux)
URE_TYPES="/usr/lib/libreoffice/program/types.rdb"
OFFICE_TYPES="/usr/lib/libreoffice/program/types/offapi.rdb"
for f in "$URE_TYPES" "$OFFICE_TYPES"; do
  if [[ ! -f "$f" ]]; then
    echo "error: missing type library $f" >&2
    exit 1
  fi
done

rm -f "$RDB_PYTHON" "$RDB_PROMPT"
"$UNOIDLWRITE" "$URE_TYPES" "$OFFICE_TYPES" "$IDL_PYTHON" "$RDB_PYTHON"
"$UNOIDLWRITE" "$URE_TYPES" "$OFFICE_TYPES" "$IDL_PROMPT" "$RDB_PROMPT"
echo "Wrote $RDB_PYTHON ($(wc -c <"$RDB_PYTHON") bytes) from XPythonFunction.idl"
echo "Wrote $RDB_PROMPT ($(wc -c <"$RDB_PROMPT") bytes) from XPromptFunction.idl"
