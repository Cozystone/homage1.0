#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT/src-tauri/target/release/bundle/macos/ATANOR.app}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[macOS verify] non-macOS host detected; skipping codesign and Gatekeeper verification."
  exit 0
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "[macOS verify] app bundle not found: $APP_PATH" >&2
  exit 1
fi

echo "[macOS verify] checking code signature: $APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
codesign -dv --verbose=4 "$APP_PATH" 2>&1 | sed 's/^/[macOS codesign] /'

echo "[macOS verify] checking Gatekeeper assessment"
spctl -a -vv --type execute "$APP_PATH" 2>&1 | sed 's/^/[macOS spctl] /'

DMG_PATH="$(find "$ROOT/src-tauri/target/release/bundle/dmg" -maxdepth 1 -name '*.dmg' -print -quit 2>/dev/null || true)"
if [[ -n "$DMG_PATH" ]]; then
  echo "[macOS verify] checking DMG assessment: $DMG_PATH"
  spctl -a -vv --type open "$DMG_PATH" 2>&1 | sed 's/^/[macOS dmg] /'
fi
