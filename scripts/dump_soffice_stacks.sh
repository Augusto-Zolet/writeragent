#!/bin/bash
# Snapshot Python + native stacks of soffice.bin (notebook-import hang).
# Usage: scripts/dump_soffice_stacks.sh [pid]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYSPY="${ROOT}/.venv/bin/py-spy"
OUT="${1:-}"
if [[ "${OUT}" =~ ^[0-9]+$ ]] || [[ -z "${OUT}" ]]; then
  PID="${OUT:-}"
  OUT=""
else
  PID="${2:-}"
fi
if [[ -z "${PID}" ]]; then
  PID="$(pgrep -n -f '/libreoffice/program/soffice.bin' || true)"
fi
if [[ -z "${PID}" ]]; then
  echo "No soffice.bin process found" >&2
  exit 1
fi
STAMP="$(date +%Y%m%d-%H%M%S)"
DIR="${ROOT}/.kilo/soffice-stacks"
mkdir -p "${DIR}"
if [[ -z "${OUT}" ]]; then
  OUT="${DIR}/${STAMP}-pid${PID}"
fi
echo "pid=${PID} out=${OUT}"
echo "=== py-spy dump --native ===" | tee "${OUT}.pyspy.txt"
if ! sudo -n "${PYSPY}" dump -p "${PID}" -n --full-filenames >>"${OUT}.pyspy.txt" 2>&1; then
  "${PYSPY}" dump -p "${PID}" -n --full-filenames >>"${OUT}.pyspy.txt" 2>&1 || true
fi
echo "=== gdb thread apply all bt ===" | tee "${OUT}.gdb.txt"
gdb -p "${PID}" -batch \
  -ex "set pagination off" \
  -ex "thread apply all bt" \
  >>"${OUT}.gdb.txt" 2>&1 || true
echo "wrote ${OUT}.pyspy.txt ${OUT}.gdb.txt"
