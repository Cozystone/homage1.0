#!/bin/sh
# ATANOR living wallpaper — single-surface desktop. firefox-esr renders it
# (Debian chromium's renderer dies on this minbase — measured); the browser
# chrome is hidden with userChrome.css instead of --kiosk, because kiosk
# fullscreen covers the taskbar while a DESKTOP-typed window sits under it.
# The surface IS the desktop: orb, icons, composer — one page, no orb window.
ok=0
while [ "$ok" -lt 2 ]; do
  if curl -sf -m 4 http://127.0.0.1:3000/shell >/dev/null 2>&1; then ok=$((ok+1)); else ok=0; fi
  sleep 5
done

# fresh profile every session: no crash-restore banners, ever
rm -rf /tmp/ffwall
mkdir -p /tmp/ffwall/chrome
cat > /tmp/ffwall/user.js <<'PREFS'
user_pref("media.navigator.permission.disabled", true);
user_pref("permissions.default.microphone", 1);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.sessionstore.max_resumed_crashes", 0);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
PREFS
cat > /tmp/ffwall/chrome/userChrome.css <<'CSSX'
/* the wallpaper surface shows NO browser — the page is the desktop */
#navigator-toolbox { visibility: collapse !important; }
CSSX

firefox-esr --new-instance --profile /tmp/ffwall \
  "http://127.0.0.1:3000/shell?wallpaper=1" &
B=$!

# once the page announces itself, pin the surface to the DESKTOP layer and
# stretch it — openbox keeps desktop-type windows below everything, and the
# taskbar (panel layer) stays visible on top
WID=""
i=0
while [ $i -lt 120 ]; do
  WID=$(xdotool search --name 'ATANOR WALLPAPER' 2>/dev/null | head -1)
  [ -n "$WID" ] && break
  i=$((i+1)); sleep 1
done
if [ -n "$WID" ]; then
  # 1) strip the WM titlebar: openbox honors live _MOTIF_WM_HINTS changes
  #    (flags=2 => DECORATIONS field valid, decorations=0 => none). This is the
  #    reliable path — firefox's --name/--class flags are unreliable on X11, and
  #    openbox ignores a post-map _NET_WM_WINDOW_TYPE change. Retry: firefox can
  #    re-assert its own decor hints while the page loads.
  # KEEPER loop, not a burst: on 1080p software-GL the page loads slowly and
  # firefox re-asserts its decor hints after a finite burst ends (measured —
  # the titlebar returned). Re-apply every 20s for the surface's lifetime.
  (
    # loop on WINDOW existence, not the launcher PID — firefox wrappers fork,
    # so $B can die while the surface lives (keeper exited instantly once)
    while xdotool getwindowname "$WID" >/dev/null 2>&1; do
      xprop -id "$WID" -f _MOTIF_WM_HINTS 32c \
        -set _MOTIF_WM_HINTS "0x2, 0x0, 0x0, 0x0, 0x0" 2>/dev/null
      wmctrl -i -r "$WID" -b add,below,sticky,skip_taskbar,skip_pager 2>/dev/null
      xdotool windowmove "$WID" 0 0 2>/dev/null
      xdotool windowsize "$WID" 100% 100% 2>/dev/null
      sleep 20
    done
  ) &
fi
wait $B
