# -*- coding: utf-8 -*-
"""Brain Link peer — the real TCP transport for two ATANOR selves (BL-1 handshake + BL-2 dialogue).
The loopback twin proved the constitution in-process; this proves it over a socket, so PC<->Radxa
is the SAME code across the wire.

  # on the Radxa (edge brain):
  python3 scripts/brain_link_peer.py --listen 8790 --id atanor-edge
  # on the PC (heavy brain):
  python  scripts/brain_link_peer.py --connect 100.108.120.104:8790 --id atanor-pc --ask "Where is the football?"

Framing: newline-delimited JSON, each message = {kind, payload, sig}. The constitution rides in the
message shapes (see packages/brain_link/protocol): signed hellos (replay/forgery refused), turns
that carry bones so G-F3 holds across the wire, and injection scanning on every inbound text. Peer
utterances are DATA — nothing here executes them.

Identity: a deterministic per-id keypair from a local seed file (so a peer keeps its id across runs);
for a first bring-up the seed is auto-created. The answer plug is the situation model over a small
local story — swap in the response workspace for the full brain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.brain_link.link_agent import LinkAgent
from packages.brain_link.protocol import (Hello, Turn, generate_identity, make_hello, make_turn)
from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer as sit_answer

SEED_DIR = REPO / "data" / "brain_link"
STORY = ("Mary moved to the bathroom. Mary got the football there. "
         "Mary journeyed to the office. Daniel went to the kitchen.")


def _identity(ai_id: str) -> tuple[str, str]:
    """Stable per-id identity: reuse the seed file if present so the peer keeps its keypair."""
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    f = SEED_DIR / f"identity_{ai_id}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["pubkey"], d["secret"]
    pub, sec = generate_identity()
    f.write_text(json.dumps({"pubkey": pub, "secret": sec}), encoding="utf-8")
    return pub, sec


def _engine(utterance: str) -> dict:
    out = sit_answer(utterance, build(STORY))
    if out.get("answer"):
        return {"reply": str(out["answer"]), "bones": [["story", "states", str(out["answer"])]],
                "evidence": [out.get("evidence", "")]}
    return {"reply": "I don't have grounded knowledge of that.", "bones": [], "evidence": []}


def _send(sock: socket.socket, obj: dict) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def _recv(f) -> dict | None:
    line = f.readline()
    return json.loads(line) if line.strip() else None


def _hello_from(d: dict) -> Hello:
    p = d["payload"]
    return Hello(ai_id=p["ai_id"], pubkey=p["pubkey"], manifest=p["manifest"], nonce=p["nonce"],
                ts=p["ts"], sig=d["sig"])


def _turn_from(d: dict) -> Turn:
    p = d["payload"]
    return Turn(speaker=p["speaker"], utterance=p["utterance"], bones=p["bones"],
                evidence=p["evidence"], ts=p["ts"], sig=d["sig"])


def run_listen(port: int, ai_id: str) -> int:
    pub, sec = _identity(ai_id)
    agent = LinkAgent(ai_id, pub, sec, _engine)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print(f"[{ai_id}] listening on :{port} (pubkey {pub[:16]}…)")
    conn, addr = srv.accept()
    print(f"[{ai_id}] peer connected from {addr[0]}")
    f = conn.makefile("r", encoding="utf-8")
    while True:
        msg = _recv(f)
        if msg is None:
            break
        if msg["kind"] == "hello":
            res = agent.receive_hello(_hello_from(msg))
            print(f"[{ai_id}] hello: accepted={res['accepted']} "
                  f"injection_findings={res.get('injection_findings')}")
            if res["accepted"]:
                back = make_hello(ai_id, pub, sec, {"tier": "edge", "organs": ["situation_model"]})
                _send(conn, {"kind": "hello", "payload": back.payload(), "sig": back.sig})
        elif msg["kind"] == "turn":
            reply = agent.receive_turn(_turn_from(msg))
            if reply is not None:
                print(f"[{ai_id}] answered '{reply.utterance}' (grounded={reply.is_grounded_claim()})")
                _send(conn, {"kind": "turn", "payload": reply.payload(), "sig": reply.sig})
    print(f"[{ai_id}] session closed. log: {len(agent.log)} events")
    return 0


def run_connect(target: str, ai_id: str, ask: str) -> int:
    host, port = target.split(":")
    pub, sec = _identity(ai_id)
    agent = LinkAgent(ai_id, pub, sec, _engine)
    sock = socket.create_connection((host, int(port)), timeout=15)
    f = sock.makefile("r", encoding="utf-8")
    hello = make_hello(ai_id, pub, sec, {"tier": "pc", "organs": ["situation_model", "realizer"]})
    _send(sock, {"kind": "hello", "payload": hello.payload(), "sig": hello.sig})
    peer_hello = _recv(f)
    if peer_hello and peer_hello["kind"] == "hello":
        res = agent.receive_hello(_hello_from(peer_hello))
        print(f"[{ai_id}] peer '{peer_hello['payload']['ai_id']}' hello accepted={res['accepted']}")
    turn = make_turn(ai_id, sec, ask)
    _send(sock, {"kind": "turn", "payload": turn.payload(), "sig": turn.sig})
    ans = _recv(f)
    if ans and ans["kind"] == "turn":
        print(f"[{ai_id}] asked: {ask!r}")
        print(f"[{ai_id}] peer replied: {ans['payload']['utterance']!r} "
              f"(grounded={bool(ans['payload']['bones'])})")
    sock.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int)
    ap.add_argument("--connect", type=str)
    ap.add_argument("--id", required=True)
    ap.add_argument("--ask", default="Where is the football?")
    a = ap.parse_args()
    if a.listen:
        return run_listen(a.listen, a.id)
    if a.connect:
        return run_connect(a.connect, a.id, a.ask)
    ap.error("need --listen PORT or --connect HOST:PORT")


if __name__ == "__main__":
    raise SystemExit(main())
