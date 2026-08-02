#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT/src-tauri/target/release/bundle/macos/ATANOR.app}"
OUT_DIR="$ROOT/dist-artifacts/macos-appstore"
PKG_PATH="$OUT_DIR/ATANOR-macOS-AppStore.pkg"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[macOS appstore] App Store packaging must run on macOS." >&2
  exit 1
fi

if [[ -z "${APPLE_INSTALLER_SIGNING_IDENTITY:-}" ]]; then
  echo "[macOS appstore] APPLE_INSTALLER_SIGNING_IDENTITY is required." >&2
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "[macOS appstore] app bundle not found: $APP_PATH" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
rm -f "$PKG_PATH"

echo "[macOS appstore] building signed installer package"
xcrun productbuild \
  --component "$APP_PATH" /Applications \
  --sign "$APPLE_INSTALLER_SIGNING_IDENTITY" \
  "$PKG_PATH"

pkgutil --check-signature "$PKG_PATH" | sed 's/^/[macOS pkg] /'
echo "[macOS appstore] package ready: $PKG_PATH"
