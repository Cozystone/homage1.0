#!/usr/bin/env bash
# ATANOR Environment — Stage 1 installer.
# Turns a stock Ubuntu 22.04/24.04 into an ATANOR machine: the engine and web shell run
# as bounded systemd services from boot, data lives in /var/lib/atanor, and (optionally)
# the machine boots straight into the ATANOR shell in kiosk mode.
#
#   sudo bash install.sh                 # services only (reach it at http://localhost:3000)
#   sudo bash install.sh --kiosk         # + boot into the full-screen orb shell ONLY
#   sudo bash install.sh --desktop       # + full GNOME desktop (install apps, browse —
#                                        #   a normal computer) with ATANOR as a resident
#                                        #   window that opens at login. Owner direction:
#                                        #   the OS must stay a general-purpose machine,
#                                        #   with the AI woven through it — not a cage.
#
# Idempotent: safe to re-run for updates (git pull + rebuild + restart).
# Honest boundaries: no kernel/driver work here — Ubuntu LTS carries that. Ctrl+Alt+F2
# always remains a normal TTY; we never lock the user in.
set -euo pipefail

REPO_URL="${ATANOR_REPO:-https://github.com/Cozystone/ATANOR-Demo.git}"
BRANCH="${ATANOR_BRANCH:-demo}"
APP_DIR=/opt/atanor
DATA_DIR=/var/lib/atanor
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIOSK=0
DESKTOP=0
[ "${1:-}" = "--kiosk" ] && KIOSK=1
[ "${1:-}" = "--desktop" ] && DESKTOP=1

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }

echo "[1/6] packages"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git python3 python3-venv python3-pip curl ca-certificates
# Node >= 20 is required by the web shell (Next 16); stock Ubuntu apt ships 18.
# NodeSource puts node+npm at /usr/bin, which is exactly what the systemd units expect.
NODE_MAJOR="$(node -e 'process.stdout.write(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
if [ "${NODE_MAJOR:-0}" -lt 20 ] || [ ! -x /usr/bin/node ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
fi
if [ "$KIOSK" -eq 1 ]; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y cage chromium-browser || \
  DEBIAN_FRONTEND=noninteractive apt-get install -y cage chromium
fi
if [ "$DESKTOP" -eq 1 ]; then
  # A real desktop: install apps, browse, use it like any computer. ATANOR rides on
  # top as a resident window, it does not replace the desktop.
  DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop-minimal chromium-browser || \
  DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop-minimal chromium
  # Windows-like bottom taskbar (Dash-to-Panel, from extensions.gnome.org — noble
  # dropped the apt package), Xorg session, dconf keyfile, perception unit: all
  # handled by the shared repair script so install and repair can never diverge.
  bash "$HERE/fix-desktop.sh"
  # OS Action Lane actuators: real desktop control (input/windows/audio/screenshot)
  DEBIAN_FRONTEND=noninteractive apt-get install -y ydotool wmctrl gnome-screenshot || true
  systemctl enable --now ydotool || systemctl enable --now ydotoold 2>/dev/null || true
  # perception stream needs xdotool to read the active window (OPT-IN daemon)
  DEBIAN_FRONTEND=noninteractive apt-get install -y xdotool || true
  mkdir -p /etc/systemd/user
  install -m 0644 "$HERE/atanor-perception.service" /etc/systemd/user/atanor-perception.service
fi

echo "[2/6] atanor system user + directories"
id -u atanor >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/atanor-home atanor
mkdir -p "$DATA_DIR"
chown -R atanor:atanor "$DATA_DIR"

echo "[3/6] code -> $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
else
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
fi
chown -R atanor:atanor "$APP_DIR"

echo "[4/6] python venv + node build"
sudo -u atanor python3 -m venv "$APP_DIR/.venv"
sudo -u atanor "$APP_DIR/.venv/bin/pip" install --upgrade pip -q
sudo -u atanor "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/deploy/requirements-cloud.txt"
# Import-path contract: the engine imports both `packages.x` (repo root on path) AND
# single-name packages (`guard`, `knowledge_bakery`, ...) exactly like the dev starter
# (PYTHONPATH = root + every packages/* dir). Encode it as a venv .pth so systemd units
# need no fragile environment list. Boot-test lesson: missing this crash-looped the
# engine with `ModuleNotFoundError: guard.checker` while web ran fine.
SITE_DIR="$(sudo -u atanor "$APP_DIR/.venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
{ echo "$APP_DIR"; echo "$APP_DIR/apps/api"; for d in "$APP_DIR"/packages/*/; do echo "${d%/}"; done; } \
  | sudo -u atanor tee "$SITE_DIR/atanor-paths.pth" >/dev/null
( cd "$APP_DIR/apps/web" && sudo -u atanor npm install --no-audit --no-fund && sudo -u atanor npm run build )

echo "[5/6] systemd services"
install -m 0644 "$HERE/atanor-engine.service" /etc/systemd/system/atanor-engine.service
install -m 0644 "$HERE/atanor-web.service" /etc/systemd/system/atanor-web.service
systemctl daemon-reload
systemctl enable --now atanor-engine.service atanor-web.service

if [ "$KIOSK" -eq 1 ]; then
  echo "[6/6] kiosk shell (boots into ATANOR; Ctrl+Alt+F2 stays a normal TTY)"
  install -m 0644 "$HERE/atanor-shell.service" /etc/systemd/system/atanor-shell.service
  systemctl enable atanor-shell.service
  systemctl set-default graphical.target
elif [ "$DESKTOP" -eq 1 ]; then
  echo "[6/6] desktop mode — GNOME + ATANOR resident window at login"
  # system-wide autostart: every user gets the orb window on login; closing it is
  # allowed (relaunch from the app grid) — the AI lives WITH the desktop, not over it.
  mkdir -p /etc/xdg/autostart
  cat > /etc/xdg/autostart/atanor-orb.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=ATANOR
Comment=Your resident intelligence — voice orb (local-only)
Exec=/usr/local/bin/atanor-orb-wallpaper
X-GNOME-Autostart-enabled=true
EOF
  cat > /usr/share/applications/atanor.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=ATANOR
Comment=Dashboard (full panels)
Exec=sh -c 'exec chromium-browser --app=http://127.0.0.1:3000 2>/dev/null || exec chromium --app=http://127.0.0.1:3000'
Categories=Utility;
EOF
  # ---- ATANOR face, from power-on to desktop (owner: 'boot must look like US') ----
  # base stays Ubuntu LTS (kernel/driver burden stays theirs); every VISIBLE surface
  # becomes ATANOR: boot splash, login screen, wallpaper, hostname pretty name.
  mkdir -p /usr/share/atanor
  cp "$APP_DIR/apps/landing/assets/atanor-logo-white-cropped.png" /usr/share/atanor/logo.png || true
  # 1) plymouth boot splash: ATANOR logo centered on black (script theme, minimal)
  if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    mkdir -p /usr/share/plymouth/themes/atanor
    cp /usr/share/atanor/logo.png /usr/share/plymouth/themes/atanor/logo.png
    cat > /usr/share/plymouth/themes/atanor/atanor.plymouth <<'EOF'
[Plymouth Theme]
Name=ATANOR
Description=ATANOR boot splash
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/atanor
ScriptFile=/usr/share/plymouth/themes/atanor/atanor.script
EOF
    cat > /usr/share/plymouth/themes/atanor/atanor.script <<'EOF'
Window.SetBackgroundTopColor(0, 0, 0);
Window.SetBackgroundBottomColor(0, 0, 0);
logo.image = Image("logo.png");
logo.sprite = Sprite(logo.image);
logo.sprite.SetX(Window.GetWidth() / 2 - logo.image.GetWidth() / 2);
logo.sprite.SetY(Window.GetHeight() / 2 - logo.image.GetHeight() / 2);
EOF
    plymouth-set-default-theme atanor || true
    update-initramfs -u || true
  fi
  # 2) login screen: ATANOR logo on the GDM greeter
  mkdir -p /etc/dconf/profile /etc/dconf/db/gdm.d
  printf 'user-db:user
system-db:gdm
file-db:/usr/share/gdm/greeter-dconf-defaults
' > /etc/dconf/profile/gdm
  cat > /etc/dconf/db/gdm.d/01-atanor <<'EOF'
[org/gnome/login-screen]
logo='/usr/share/atanor/logo.png'
EOF
  # 3) desktop defaults: black wallpaper with the centered ATANOR mark, dock favorites
  mkdir -p /etc/dconf/db/local.d
  printf 'user-db:user
system-db:local
' > /etc/dconf/profile/user
  # keyfile lives in the repo (single source of truth; see dconf/01-atanor for the
  # duplicate-group hard rule that once silently broke the whole desktop)
  install -m 0644 "$HERE/dconf/01-atanor" /etc/dconf/db/local.d/01-atanor
  dconf update || true
  # 4) identity strings
  command -v hostnamectl >/dev/null 2>&1 && hostnamectl set-hostname --pretty "ATANOR" || true
  # ATANOR orb overlay: install + enable the GNOME extension that pins the orb window
  EXT_UUID=atanor-orb@atanor.ai
  install -d /usr/share/gnome-shell/extensions/$EXT_UUID
  cp "$HERE/gnome-extension/$EXT_UUID/"* /usr/share/gnome-shell/extensions/$EXT_UUID/ 2>/dev/null || true
  # NOTE: the extension is enabled in the single [org/gnome/shell] section above —
  # dconf keyfiles REJECT duplicate group headers (the whole db fails to compile,
  # silently killing wallpaper/panel/extensions), so never append a second section.
  # Fail LOUDLY if the keyfile ever breaks again:
  dconf compile /tmp/atanor-dconf-test.db /etc/dconf/db/local.d && rm -f /tmp/atanor-dconf-test.db
  systemctl set-default graphical.target
else
  echo "[6/6] no kiosk requested — open http://localhost:3000"
fi

echo
echo "ATANOR Environment installed."
echo "  engine : systemctl status atanor-engine   (health: curl http://127.0.0.1:8502/health)"
echo "  shell  : http://localhost:3000"
echo "  data   : $DATA_DIR   (backup = copy this directory)"
