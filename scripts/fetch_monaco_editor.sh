#!/usr/bin/env bash
# Bundle Monaco min files into plugin/scripting/assets/editor/vs/
set -euo pipefail
VERSION="${MONACO_VERSION:-0.52.2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/plugin/scripting/assets/editor"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "https://registry.npmjs.org/monaco-editor/-/monaco-editor-${VERSION}.tgz" -o "$TMP/monaco.tgz"
tar -xzf "$TMP/monaco.tgz" -C "$TMP"
rm -rf "$DEST/vs"
cp -r "$TMP/package/min/vs" "$DEST/vs"
echo "Monaco ${VERSION} installed under $DEST/vs"
