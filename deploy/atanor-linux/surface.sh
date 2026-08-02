#!/bin/sh
# ATANOR pure surface — the post-window desktop. cage owns the screen: there is
# no window manager, no titlebar, no taskbar, no decoration ANYWHERE, because
# the concepts do not exist in this session. The surface (orb, field, icons,
# composer, trust dial, pairing chip) is the entire screen.
# firefox remains ONLY as a chrome-less renderer for the surface; it is removed
# entirely at 2b-M2 when the compositor draws the field natively.
ok=0
while [ "$ok" -lt 2 ]; do
  if curl -sf -m 4 http://127.0.0.1:3000/shell >/dev/null 2>&1; then ok=$((ok+1)); else ok=0; fi
  sleep 5
done
rm -rf /tmp/ffsurface
mkdir -p /tmp/ffsurface
cat > /tmp/ffsurface/user.js <<'PREFS'
user_pref("media.navigator.permission.disabled", true);
user_pref("permissions.default.microphone", 1);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.sessionstore.max_resumed_crashes", 0);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("full-screen-api.ignore-widgets", true);
PREFS
# KOREAN INPUT: fcitx5+hangul rides XWayland/XIM — cage's Wayland text-input
# support is not guaranteed, XIM is boring-reliable. firefox therefore runs as
# an XWayland client here (MOZ_ENABLE_WAYLAND unset on purpose).
# NOTE: Ctrl+Space belongs to 한/영 toggle; the omni-prompt answers to '/'.
export GTK_IM_MODULE=fcitx
export QT_IM_MODULE=fcitx
export XMODIFIERS=@im=fcitx
command -v fcitx5 >/dev/null 2>&1 && fcitx5 -d >/dev/null 2>&1 &
sleep 1
exec firefox-esr --kiosk --new-instance --profile /tmp/ffsurface \
  "http://127.0.0.1:3000/shell?wallpaper=1"
