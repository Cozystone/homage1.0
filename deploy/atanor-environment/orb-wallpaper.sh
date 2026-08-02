#!/bin/sh
# ATANOR living wallpaper — the redesign the owner asked for: not a floating
# window but the DESKTOP LAYER itself. We launch the shell surface fullscreen,
# then retype the X11 window to _NET_WM_WINDOW_TYPE_DESKTOP: mutter re-reads the
# type and moves it under every app window, undecorated, sticky — the SPLATRA
# particle field IS the wallpaper, and clicking the empty desktop talks to the orb.
# No own-OS required for this; the compositor treats the wallpaper as just
# another surface. (Xorg session; the own-compositor stage-2 does this natively.)
# STABLE web, not just alive: at first boot the web unit cycles with the engine
# (Requires=), and a surface launched into a down-window keeps an error page
# forever. Two consecutive 200s five seconds apart = actually up.
ok=0
while [ "$ok" -lt 2 ]; do
  if curl -sf -m 4 http://127.0.0.1:3000/shell >/dev/null 2>&1; then ok=$((ok+1)); else ok=0; fi
  sleep 5
done
U="http://127.0.0.1:3000/shell?wallpaper=1"
(chromium-browser --app="$U" --start-fullscreen 2>/dev/null \
  || chromium --app="$U" --start-fullscreen) &
BROWSER=$!

# the page renames itself to 'ATANOR WALLPAPER' so we retype exactly this surface
WID=""
i=0
while [ $i -lt 90 ]; do
  WID=$(xdotool search --name '^ATANOR WALLPAPER$' 2>/dev/null | head -1)
  [ -n "$WID" ] && break
  i=$((i+1)); sleep 1
done
if [ -n "$WID" ]; then
  xprop -id "$WID" -f _NET_WM_WINDOW_TYPE 32a \
    -set _NET_WM_WINDOW_TYPE _NET_WM_WINDOW_TYPE_DESKTOP
fi
wait $BROWSER
