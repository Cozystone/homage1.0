#!/usr/bin/env bash
# ATANOR Environment — ISO remaster (Stage 1, "설치하면 곧 ATANOR").
# Takes a stock Ubuntu 24.04 Server ISO, injects the autoinstall seed + boot flags, and
# produces atanor-environment-amd64.iso. The installed system provisions itself on first
# boot (atanor-firstboot.service -> install.sh --kiosk).
#
#   sudo bash make_iso.sh /path/to/ubuntu-24.04-live-server-amd64.iso [out.iso]
#
# Requires: xorriso (apt-get install -y xorriso). Runs anywhere Linux (WSL fine).
set -euo pipefail

SRC_ISO="${1:?usage: make_iso.sh <ubuntu-server.iso> [out.iso]}"
OUT_ISO="${2:-atanor-environment-amd64.iso}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d /tmp/atanor-iso.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

command -v xorriso >/dev/null || { apt-get update -y && apt-get install -y xorriso; }

echo "[1/4] extract ISO"
xorriso -osirrox on -indev "$SRC_ISO" -extract / "$WORK/iso" >/dev/null 2>&1
chmod -R u+w "$WORK/iso"

echo "[2/4] inject autoinstall seed (nocloud)"
mkdir -p "$WORK/iso/atanor"
cp "$HERE/autoinstall/user-data" "$WORK/iso/atanor/user-data"
touch "$WORK/iso/atanor/meta-data"

echo "[3/4] boot flags -> autoinstall"
# GRUB (UEFI + BIOS both read boot/grub/grub.cfg on Ubuntu live-server).
# console=ttyS0 secondary so headless/VM runs stream kernel+installer logs to serial
# (tty1 stays primary — the physical screen keeps the normal installer output).
sed -i 's|---|autoinstall ds=nocloud\\;s=/cdrom/atanor/ console=ttyS0,115200 console=tty1 ---|' "$WORK/iso/boot/grub/grub.cfg"
grep -q "autoinstall" "$WORK/iso/boot/grub/grub.cfg" || { echo "grub patch failed"; exit 1; }

echo "[4/4] rebuild hybrid ISO (replaying the source ISO's own boot layout)"
# Version-proof: ask xorriso how the SOURCE ISO was built and replay those exact
# El-Torito/GPT options against our modified tree — no hardcoded boot-image paths.
REPLAY="$WORK/replay.sh"
{
  printf 'xorriso -as mkisofs -r -V ATANOR-ENV -o "%s" ' "$OUT_ISO"
  xorriso -indev "$SRC_ISO" -report_el_torito as_mkisofs 2>/dev/null | tr '\n' ' '
  printf ' "%s"\n' "$WORK/iso"
} > "$REPLAY"
bash "$REPLAY" >/dev/null 2>&1

echo "done: $OUT_ISO ($(du -h "$OUT_ISO" | cut -f1))"
echo "flash with balenaEtcher/rufus; installed machine provisions itself on first boot."
