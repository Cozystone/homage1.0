#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHANNEL="${1:-developer-id}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[macOS preflight] missing required command: $1" >&2
    exit 1
  fi
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "[macOS preflight] missing required environment variable: $name" >&2
    exit 1
  fi
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[macOS preflight] macOS packaging must run on a macOS runner or Mac workstation." >&2
  exit 1
fi

require_command node
require_command npm
require_command python3
require_command rustc
require_command cargo
require_command xcrun
require_command codesign
require_command spctl

case "$CHANNEL" in
  developer-id)
    require_env APPLE_SIGNING_IDENTITY
    require_env APPLE_ID
    require_env APPLE_PASSWORD
    require_env APPLE_TEAM_ID
    ;;
  app-store)
    require_env APPLE_SIGNING_IDENTITY
    require_env APPLE_INSTALLER_SIGNING_IDENTITY
    ;;
  *)
    echo "[macOS preflight] unknown channel: $CHANNEL" >&2
    exit 1
    ;;
esac

echo "[macOS preflight] channel=$CHANNEL"
echo "[macOS preflight] root=$ROOT"
rustc -vV | sed 's/^/[macOS preflight] /'
