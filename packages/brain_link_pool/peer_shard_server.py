# -*- coding: utf-8 -*-
"""Peer shard server — the TRANSPORT layer of distributed tensor sharding.

One Brain Link peer = one process holding one shard slice (.npz of s/p/o
columns) and answering shard ops over HTTP. Every request is HMAC-signed
(shared pool secret v1; peer_trust_guard's per-peer keys slot into the same
header) — an unsigned or mis-signed request is refused before any compute.

The peer only ever returns a CLAIM. The coordinator verifies it against its
authoritative copy of the slice (see peer_transport.RemoteShard) — the same
requester-re-runs-a-sample model as render economies, which is why a lying
peer process is caught by the router, never trusted by it.

Run:  python -m packages.brain_link_pool.peer_shard_server \
          --slice shard0.npz --port 18871
Env:  ATANOR_PEER_SECRET (shared pool secret), ATANOR_PEER_LIE=1 (test-only
      fault injection: inflates degree claims so verification can be shown
      catching a dishonest peer)."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class ShardHandler(BaseHTTPRequestHandler):
    slice_data: dict = {}
    secret: str = ""
    lie: bool = False

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        sig = self.headers.get("X-Atanor-Sig", "")
        if not hmac.compare_digest(sig, sign(self.secret, body)):
            return self._send(403, {"error": "bad signature"})
        try:
            req = json.loads(body)
            op, cid = req["op"], int(req.get("cid", -1))
        except Exception:
            return self._send(400, {"error": "bad request"})
        s, o = self.slice_data["s"], self.slice_data["o"]
        if op == "degree":
            claim = int((s == cid).sum()) + (100 if self.lie else 0)
        elif op == "neighbors":
            claim = sorted(int(x) for x in o[s == cid].tolist())
        elif op == "rows":
            claim = int(len(s))
        else:
            return self._send(400, {"error": f"unknown op {op}"})
        self._send(200, {"claim": claim,
                         "shard_id": int(self.slice_data.get("shard_id", -1))})

    def _send(self, code: int, obj: dict):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):  # quiet
        pass


def make_server(slice_path: str, port: int, secret: str,
                lie: bool = False) -> ThreadingHTTPServer:
    z = np.load(slice_path)
    handler = type("H", (ShardHandler,), {
        "slice_data": {"s": z["s"], "o": z["o"], "shard_id": int(z["shard_id"])},
        "secret": secret, "lie": lie})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", required=True)
    ap.add_argument("--port", type=int, required=True)
    args = ap.parse_args()
    srv = make_server(args.slice, args.port,
                      os.environ.get("ATANOR_PEER_SECRET", "atanor-pool"),
                      lie=os.environ.get("ATANOR_PEER_LIE") == "1")
    print(f"peer shard serving :{args.port}", flush=True)
    srv.serve_forever()
