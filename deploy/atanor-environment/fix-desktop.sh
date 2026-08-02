#!/usr/bin/env bash
# Quick desktop-branding repair: reinstall the dconf keyfile + orb extension and
# VERIFY the db compiles (the failure mode that left the desktop looking stock).
# Safe to re-run; does not touch services or rebuild anything.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }

mkdir -p /etc/dconf/profile /etc/dconf/db/local.d
printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user
install -m 0644 "$HERE/dconf/01-atanor" /etc/dconf/db/local.d/01-atanor

EXT_UUID=atanor-orb@atanor.ai
install -d /usr/share/gnome-shell/extensions/$EXT_UUID
cp "$HERE/gnome-extension/$EXT_UUID/"* /usr/share/gnome-shell/extensions/$EXT_UUID/

dconf update
dconf compile /tmp/atanor-dconf-test.db /etc/dconf/db/local.d
rm -f /tmp/atanor-dconf-test.db
echo "DCONF-COMPILE-OK"

# Dash-to-Panel: NOT packaged in noble (24.04) — install from the official GNOME
# extensions site (the canonical channel), matched to the running shell version.
FAIL=0
DTP=dash-to-panel@jderose9.github.com
if [ ! -d /usr/share/gnome-shell/extensions/$DTP ]; then
  SHELL_V="$(gnome-shell --version 2>/dev/null | grep -o '[0-9]*' | head -1 || echo 46)"
  DL="$(curl -sf "https://extensions.gnome.org/extension-info/?uuid=$DTP&shell_version=$SHELL_V" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["download_url"])' 2>/dev/null || true)"
  if [ -n "$DL" ] && curl -sfL "https://extensions.gnome.org$DL" -o /tmp/dtp.zip; then
    mkdir -p /usr/share/gnome-shell/extensions/$DTP
    python3 -c "import zipfile; zipfile.ZipFile('/tmp/dtp.zip').extractall('/usr/share/gnome-shell/extensions/$DTP')"
    # system-wide extensions must not carry per-user schema compilation leftovers
    command -v glib-compile-schemas >/dev/null 2>&1 && \
      [ -d /usr/share/gnome-shell/extensions/$DTP/schemas ] && \
      glib-compile-schemas /usr/share/gnome-shell/extensions/$DTP/schemas || true
    rm -f /tmp/dtp.zip
    echo "DTP-INSTALLED (shell $SHELL_V)"
  else
    echo "DTP-DOWNLOAD-FAILED"; FAIL=1
  fi
fi

# Xorg session (xdotool active-window sensing is Xorg-only for now)
if [ -f /etc/gdm3/custom.conf ] && ! grep -q '^WaylandEnable=false' /etc/gdm3/custom.conf; then
  sed -i 's/^#\?WaylandEnable=.*/WaylandEnable=false/' /etc/gdm3/custom.conf
  grep -q '^WaylandEnable=false' /etc/gdm3/custom.conf || sed -i '/^\[daemon\]/a WaylandEnable=false' /etc/gdm3/custom.conf
fi

# perception daemon (user unit; OPT-IN — enabled per-user, not here)
mkdir -p /etc/systemd/user
install -m 0644 "$HERE/atanor-perception.service" /etc/systemd/user/atanor-perception.service
command -v xdotool >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y xdotool

# living wallpaper launcher (autostart Exec points here; retypes the surface
# to the DESKTOP layer so SPLATRA runs as the wallpaper itself)
install -m 0755 "$HERE/orb-wallpaper.sh" /usr/local/bin/atanor-orb-wallpaper
command -v xprop >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y x11-utils

echo "--- diagnostics ---"
ls /usr/share/gnome-shell/extensions/
command -v chromium chromium-browser firefox 2>/dev/null || true
[ -f /etc/xdg/autostart/atanor-orb.desktop ] && echo "AUTOSTART-OK" || echo "AUTOSTART-MISSING"
[ -f /usr/share/atanor/logo.png ] && echo "LOGO-OK" || echo "LOGO-MISSING"
grep -q '^WaylandEnable=false' /etc/gdm3/custom.conf 2>/dev/null && echo "XORG-OK" || echo "XORG-NOT-SET"
echo "reboot (or log out/in) to apply"
exit $FAIL
