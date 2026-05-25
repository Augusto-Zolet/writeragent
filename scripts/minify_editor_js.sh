#!/usr/bin/env bash
# Re-minify all JS under plugin/scripting/assets/editor (strip comments; in-place).
# Requires Node.js (npx terser). Omits -m so AMD define("vs/…") module ids stay intact.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EDITOR_ASSETS="$ROOT/plugin/scripting/assets/editor"
TERSER_VERSION="${TERSER_VERSION:-5.37.0}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"

if [[ ! -d "$EDITOR_ASSETS" ]]; then
  echo "minify_editor_js: missing $EDITOR_ASSETS" >&2
  exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "minify_editor_js: npx not found; install Node.js" >&2
  exit 1
fi

before_bytes=0
after_bytes=0
count=0

while IFS= read -r -d '' f; do
  size_before=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  before_bytes=$((before_bytes + size_before))
  tmp="$(mktemp)"
  if ! npx --yes "terser@${TERSER_VERSION}" "$f" --compress --comments false -o "$tmp"; then
    rm -f "$tmp"
    echo "minify_editor_js: terser failed on $f" >&2
    exit 1
  fi
  mv "$tmp" "$f"
  size_after=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  after_bytes=$((after_bytes + size_after))
  count=$((count + 1))
done < <(find "$EDITOR_ASSETS" -name '*.js' -type f -print0)

saved=$((before_bytes - after_bytes))
echo "minify_editor_js: ${count} files, $(numfmt --to=iec-i --suffix=B "$before_bytes" 2>/dev/null || echo "${before_bytes} bytes") -> $(numfmt --to=iec-i --suffix=B "$after_bytes" 2>/dev/null || echo "${after_bytes} bytes"), saved $(numfmt --to=iec-i --suffix=B "$saved" 2>/dev/null || echo "${saved} bytes")"
