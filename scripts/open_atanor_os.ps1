# Open the ATANOR OS test VM in a browser tab (noVNC over QEMU websocket VNC).
# WSLg cannot surface QEMU's GTK window on this machine (verified 2026-07-06), so the
# stable path is: QEMU -vnc :5,websocket=5705 inside WSL + noVNC served on :6080.
# Everything binds to 127.0.0.1 — nothing is exposed off-machine.
$ErrorActionPreference = "SilentlyContinue"

# NOTE: this .ps1 is CRLF on disk, so the here-string body carries \r into every
# line — bash then splits the qemu command at each \r ("-enable-kvm: command not
# found"). Strip \r before handing the script to WSL bash. Also: pgrep -f would
# match bash's own argv (the script text contains "qemu-system"), so use pidof.
$vmScript = @'
set -e
ls /opt/novnc/vnc.html >/dev/null 2>&1 || git clone --depth 1 https://github.com/novnc/noVNC.git /opt/novnc
pidof qemu-system-x86_64 >/dev/null || {
  systemctl reset-failed atanor-gui 2>/dev/null || true
  systemd-run --unit=atanor-gui --collect /usr/bin/qemu-system-x86_64 \
    -enable-kvm -cpu host -m 4096 -smp 4 \
    -drive file=/opt/atanor-iso/atanor-test.qcow2,format=qcow2,if=virtio \
    -netdev user,id=n0,hostfwd=tcp:127.0.0.1:18502-:8502,hostfwd=tcp:127.0.0.1:13000-:3000 \
    -device virtio-net-pci,netdev=n0 -vga virtio \
    -display none -vnc 127.0.0.1:5,websocket=5705,share=force-shared \
    -serial telnet:127.0.0.1:4441,server,nowait \
    -qmp unix:/tmp/atanor-qmp.sock,server,nowait
}
systemctl is-active atanor-novnc >/dev/null 2>&1 || {
  systemctl reset-failed atanor-novnc 2>/dev/null || true
  systemd-run --unit=atanor-novnc --collect python3 -m http.server 6080 --directory /opt/novnc --bind 127.0.0.1
}
echo ready
'@
$vmScript = $vmScript -replace "`r", ""
wsl -u root -- bash -c $vmScript

Start-Sleep -Seconds 3
Start-Process "http://localhost:6080/vnc.html?host=localhost&port=5705&path=&autoconnect=true&resize=scale"
Write-Output "ATANOR OS opened in the browser. Login: atanor-admin"
