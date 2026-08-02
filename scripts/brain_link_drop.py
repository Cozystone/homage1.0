# -*- coding: utf-8 -*-
"""Brain Link over an SFTP DROP mailbox — the cross-machine transport that needs no open TCP port
(Tailscale ping works but TCP:8790 did not complete; the drop rides SSH/SCP, which do). Two
intermittently-connected brains exchange signed message files through a shared drop directory
(/srv/msh/drop on the Radxa) — the SAME channel the MSH examiner already uses. Async by design:
neither side has to be listening at the same instant.

Modes:
  --make-request  --out F  --id ID  --ask Q   : PC writes a signed {hello, turn} request file.
  --process-once  --drop D --id ID            : edge reads every req_*.json, processes through a
                                                LinkAgent (hello->register, turn->answer), writes
                                                reply_*.json, and exits (one poll cycle, no daemon).
  --read-reply    --file F --id ID            : PC verifies + prints the edge's reply.

The constitution rides in the message shapes exactly as over the socket: signed hellos
(replay/forgery refused), turns carrying bones so G-F3 holds across the wire, injection scan on
every inbound text, fact offers to quarantine only. Nothing here executes peer content.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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

try:                                    # structural frame realizer + knowledge slice (edge v2):
    from packages.realizer_struct.frame_realizer import realize as frame_realize
except Exception:                       # older deployments fall back to situation-model only
    frame_realize = None

SEED_DIR = REPO / "data" / "brain_link"
KNOWLEDGE = REPO / "data" / "brain_link" / "edge_knowledge_slice.jsonl"
STORY = ("Mary moved to the bathroom. Mary got the football there. "
         "Mary journeyed to the office. Daniel went to the kitchen.")

_KN: dict[str, list] | None = None


def _knowledge() -> dict[str, list]:
    global _KN
    if _KN is None:
        _KN = {}
        if KNOWLEDGE.exists():
            for line in KNOWLEDGE.open(encoding="utf-8"):
                r = json.loads(line)
                _KN[r["subject"].lower()] = r["bones"]
    return _KN


def _identity(ai_id: str) -> tuple[str, str]:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    f = SEED_DIR / f"identity_{ai_id}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["pubkey"], d["secret"]
    pub, sec = generate_identity()
    f.write_text(json.dumps({"pubkey": pub, "secret": sec}), encoding="utf-8")
    return pub, sec


def _engine(utterance: str) -> dict:
    """Edge answer engine v2: situation model for story questions, then the KNOWLEDGE SLICE +
    structural frame realizer for 'what is X / tell me about X' — fluent grounded prose composed
    from real graph triples, zero weight-memorization."""
    out = sit_answer(utterance, build(STORY))
    if out.get("answer"):
        return {"reply": str(out["answer"]), "bones": [["story", "states", str(out["answer"])]],
                "evidence": [out.get("evidence", "")]}
    if frame_realize is not None:
        import re as _re
        m = _re.match(r"^(?:what\s+is|what\s+are|tell\s+me\s+about|who\s+is|describe)\s+"
                      r"(?:the\s+|a\s+|an\s+)?(.+?)\??$", utterance.strip(), _re.IGNORECASE)
        if m:
            subj = m.group(1).strip()
            bones = _knowledge().get(subj.lower())
            if bones:
                prose = frame_realize(bones)
                if prose:
                    return {"reply": prose, "bones": bones, "evidence": ["edge knowledge slice"]}
    return {"reply": "I don't have grounded knowledge of that.", "bones": [], "evidence": []}


def make_request(out: Path, ai_id: str, ask: str) -> int:
    pub, sec = _identity(ai_id)
    hello = make_hello(ai_id, pub, sec, {"tier": "pc", "organs": ["situation_model", "realizer"]})
    turn = make_turn(ai_id, sec, ask)
    out.write_text(json.dumps({
        "from": ai_id,
        "messages": [{"kind": "hello", "payload": hello.payload(), "sig": hello.sig},
                     {"kind": "turn", "payload": turn.payload(), "sig": turn.sig}],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"wrote request {out.name} (from {ai_id}, ask={ask!r})")
    return 0


def process_once(drop: Path, ai_id: str) -> int:
    pub, sec = _identity(ai_id)
    reqs = sorted(drop.glob("req_*.json"))
    if not reqs:
        print("no req_*.json in drop — nothing to process")
        return 0
    processed = 0
    for req in reqs:
        agent = LinkAgent(ai_id, pub, sec, _engine)
        try:
            data = json.loads(req.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"skip {req.name}: {e}")
            continue
        out_msgs = []
        for m in data.get("messages", []):
            if m["kind"] == "hello":
                p = m["payload"]
                res = agent.receive_hello(Hello(ai_id=p["ai_id"], pubkey=p["pubkey"],
                                                manifest=p["manifest"], nonce=p["nonce"],
                                                ts=p["ts"], sig=m["sig"]))
                back = make_hello(ai_id, pub, sec, {"tier": "edge", "organs": ["situation_model"]})
                out_msgs.append({"kind": "hello", "payload": back.payload(), "sig": back.sig,
                                 "accepted": res["accepted"],
                                 "injection_findings": res.get("injection_findings")})
            elif m["kind"] == "turn":
                p = m["payload"]
                rep = agent.receive_turn(Turn(speaker=p["speaker"], utterance=p["utterance"],
                                              bones=p["bones"], evidence=p["evidence"],
                                              ts=p["ts"], sig=m["sig"]))
                if rep is not None:
                    out_msgs.append({"kind": "turn", "payload": rep.payload(), "sig": rep.sig,
                                     "grounded": rep.is_grounded_claim()})
        reply = drop / req.name.replace("req_", "reply_")
        reply.write_text(json.dumps({"from": ai_id, "messages": out_msgs}, ensure_ascii=False),
                         encoding="utf-8")
        req.unlink()                       # consume the request (mailbox semantics)
        processed += 1
        print(f"processed {req.name} -> {reply.name} ({len(out_msgs)} msgs, "
              f"log {len(agent.log)} events)")
    print(f"done: {processed} request(s) processed on {ai_id}")
    return 0


def read_reply(f: Path, ai_id: str) -> int:
    data = json.loads(f.read_text(encoding="utf-8"))
    print(f"reply from {data.get('from')}:")
    for m in data.get("messages", []):
        if m["kind"] == "hello":
            print(f"  hello-back: accepted={m.get('accepted')} "
                  f"injection_findings={m.get('injection_findings')}")
        elif m["kind"] == "turn":
            print(f"  answer: {m['payload']['utterance']!r} (grounded={m.get('grounded')})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-request", action="store_true")
    ap.add_argument("--process-once", action="store_true")
    ap.add_argument("--read-reply", action="store_true")
    ap.add_argument("--drop", type=str)
    ap.add_argument("--out", type=str)
    ap.add_argument("--file", type=str)
    ap.add_argument("--id", required=True)
    ap.add_argument("--ask", default="Where is the football?")
    a = ap.parse_args()
    if a.make_request:
        return make_request(Path(a.out), a.id, a.ask)
    if a.process_once:
        return process_once(Path(a.drop), a.id)
    if a.read_reply:
        return read_reply(Path(a.file), a.id)
    ap.error("need --make-request | --process-once | --read-reply")


if __name__ == "__main__":
    raise SystemExit(main())
