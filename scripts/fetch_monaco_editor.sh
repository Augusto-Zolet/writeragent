#!/usr/bin/env bash
# Bundle Monaco min files into plugin/scripting/assets/editor/vs/, prune for Python-only, minify JS.
set -euo pipefail
VERSION="${MONACO_VERSION:-0.52.2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/plugin/scripting/assets/editor"
SCRIPTS="$ROOT/scripts"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "https://registry.npmjs.org/monaco-editor/-/monaco-editor-${VERSION}.tgz" -o "$TMP/monaco.tgz"
tar -xzf "$TMP/monaco.tgz" -C "$TMP"
rm -rf "$DEST/vs"
cp -r "$TMP/package/min/vs" "$DEST/vs"
echo "Monaco ${VERSION} installed under $DEST/vs"
"$SCRIPTS/prune_monaco_vs.sh"
"$SCRIPTS/minify_editor_js.sh"
du -sh "$DEST" "$DEST/vs" 2>/dev/null || true
