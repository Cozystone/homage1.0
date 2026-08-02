# -*- coding: utf-8 -*-
"""Autonomous Brain Link daemon — leave two of these connected and they converse (or act) on their
OWN, no external orchestrator.

Owner (2026-07-21): don't design an orchestrator; just leave the two agents connected and let them
talk or move spontaneously. Each machine runs this loop:
  - POLL the shared drop for messages addressed to me -> answer via my engine (frame realizer /
    situation model), learn, spawn new curiosity (web-searched, source-weighted, when I lack it).
  - When IDLE (no incoming) and I have curiosity pressure -> INITIATE: send the peer a question.
So conversation is self-sustaining: neither waits to be driven. Rate-limited (a polite pace) and
bounded. The constitution rides in the message shapes (signed, bones-carrying, injection-scanned).

  python scripts/brain_link_daemon.py --id atanor-pc  --peer atanor-edge --drop /srv/msh/drop
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.brain_link.conversation import Agent, Turn, step
from scripts.edge_converse_step import _load_agent, _seed_curiosity   # reuse edge state loader

IDLE_INITIATE_S = 45          # if nobody spoke to me for this long, I start a thought myself
PACE_S = 8                    # polite poll cadence
TRANSCRIPT = REPO / "data" / "brain_link" / "overnight_transcript.log"


def _pc_agent(max_subjects: int = 6000) -> Agent:
    """The PC side loads a slice of its own mined graph so it has BOTH knowledge to teach and
    curiosity (self-derived gaps) to drive the conversation — symmetric with the edge."""
    knowledge: dict = {}
    src = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
    if src.exists():
        for line in src.open(encoding="utf-8"):
            r = json.loads(line)
            s = r["subject"].lower()
            if s not in knowledge:
                if len(knowledge) >= max_subjects:
                    break
                knowledge[s] = []
            for b in r["bones"]:
                if b not in knowledge[s] and len(knowledge[s]) < 6:
                    knowledge[s].append(b)
    return Agent(ai_id="atanor-pc", knowledge=knowledge, curiosity=_seed_curiosity(knowledge),
                 web=True)


def _log_turn(t: Turn) -> None:
    """Append every utterance to a human-readable overnight transcript (checked in the morning)."""
    TRANSCRIPT.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H:%M:%S")
    src = f"  [web:{t.source}]" if getattr(t, "source", "") else ""
    with TRANSCRIPT.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}  {t.speaker:>11} > {t.text}{src}\n")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--peer", required=True)
    ap.add_argument("--drop", required=True)
    ap.add_argument("--ticks", type=int, default=0)          # 0 = forever; N = bounded (tests)
    a = ap.parse_args()
    drop = Path(a.drop)
    drop.mkdir(parents=True, exist_ok=True)
    agent = _load_agent() if a.id == "atanor-edge" else _pc_agent()
    inbox = f"to_{a.id}_"
    outbox = f"to_{a.peer}_"
    last_heard = 0.0              # start idle so whoever boots first opens the conversation
    seq = 0
    tick = 0
    while a.ticks == 0 or tick < a.ticks:
        tick += 1
        # 1) drain any messages addressed to me
        msgs = sorted(drop.glob(f"{inbox}*.json"))
        incoming = None
        for m in msgs:
            try:
                incoming = Turn(**json.loads(m.read_text(encoding="utf-8")))
            except Exception:
                incoming = None
            m.unlink(missing_ok=True)
            if incoming is not None:
                last_heard = time.time()
                _log_turn(incoming)                       # record what I heard
                reply = step(agent, incoming)
                seq += 1
                (drop / f"{outbox}{a.id}_{seq}.json").write_text(
                    json.dumps(reply.__dict__, ensure_ascii=False), encoding="utf-8")
                _log_turn(reply)                          # record what I said back
        # 2) idle + curiosity -> initiate a thought myself (self-sustaining, no orchestrator)
        if incoming is None and (time.time() - last_heard) > IDLE_INITIATE_S and agent.curiosity:
            opener = step(agent, None)
            if opener.act == "ask":
                seq += 1
                (drop / f"{outbox}{a.id}_{seq}.json").write_text(
                    json.dumps(opener.__dict__, ensure_ascii=False), encoding="utf-8")
                _log_turn(opener)
                last_heard = time.time()
        time.sleep(PACE_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
