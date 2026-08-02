#!/bin/sh
# The resident orb — firefox-esr runtime: floating, undecorated (MOTIF hints),
# always-on-top+sticky. (Debian's chromium renderer produced 0-byte DOM for
# every URL on this minbase image; firefox renders fine — measured.)
# STABLE web, not just alive: at first boot the web unit cycles with the engine
# (Requires=), and a surface launched into a down-window keeps an error page
# forever. Two consecutive 200s five seconds apart = actually up.
ok=0
while [ "$ok" -lt 2 ]; do
  if curl -sf -m 4 http://127.0.0.1:3000/shell >/dev/null 2>&1; then ok=$((ok+1)); else ok=0; fi
  sleep 5
done
mkdir -p /tmp/fforb
cat > /tmp/fforb/user.js <<'PREFS'
user_pref("media.navigator.permission.disabled", true);
user_pref("permissions.default.microphone", 1);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
PREFS
firefox-esr --new-instance --profile /tmp/fforb --width 560 --height 620 \
  "http://127.0.0.1:3000/shell?overlay=1" &
BROWSER=$!
WID=""
i=0
while [ $i -lt 120 ]; do
  for w in $(xdotool search --name 'ATANOR' 2>/dev/null); do
    name=$(xdotool getwindowname "$w" 2>/dev/null)
    case "$name" in
      *WALLPAPER*) ;;                  # the wallpaper surface is not the orb
      *ATANOR*) WID=$w; break ;;
    esac
  done
  [ -n "$WID" ] && break
  i=$((i+1)); sleep 1
done
if [ -n "$WID" ]; then
  xprop -id "$WID" -f _MOTIF_WM_HINTS 32c -set _MOTIF_WM_HINTS "2, 0, 0, 0, 0"
  wmctrl -i -r "$WID" -b add,above,sticky || true
fi
wait $BROWSER
