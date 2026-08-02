# -*- coding: utf-8 -*-
"""OPS LAN relay — the operator dashboard on the owner's PHONE, without opening the engine.

Owner (2026-07-11): " OPS ?" The engine deliberately binds 127.0.0.1 (hardened);
we do NOT rebind it. This tiny relay binds the LAN (0.0.0.0:8510) and forwards EXACTLY three
read-only GET paths to the local engine — nothing else exists here (no chat, no learning, no
mutation endpoints). Same-Wi-Fi phone → http://<PC-LAN-IP>:8510/ops

Threat posture: read-only telemetry, LAN-only (never port-forwarded), allowlist routing,
no request bodies accepted. Windows Firewall will ask once for python inbound — allow on
Private networks only.
"""
from __future__ import annotations

import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENGINE = "http://127.0.0.1:8502"
ALLOW = {"/ops", "/api/ops/overview", "/api/expedition/activity", "/health"}
PORT = 8510


class _Relay(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib contract
        path = self.path.split("?")[0]
        if path == "/":
            path = "/ops"
        if path not in ALLOW:
            self.send_response(404)
            self.end_headers()
            return
        try:
            with urllib.request.urlopen(ENGINE + path, timeout=20) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "application/json")
        except Exception:
            body = b'{"error": "engine unreachable"}'
            ctype = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):  # quiet
        pass


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", PORT), _Relay).serve_forever()


if __name__ == "__main__":
    main()
