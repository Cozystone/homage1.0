# -*- coding: utf-8 -*-
"""OBSERVE an autonomous conversation between the PC brain and the Radxa edge brain — no
interference. The PC agent runs here (larger knowledge slice); the edge agent runs ON the Radxa
(its own state file, its own web access from that box). Each turn crosses the wire over SSH. The
observer only relays sealed turns and records; it never edits an utterance.

  python scripts/observe_conversation.py [--turns 14]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.brain_link.conversation import Agent, Turn, step, _correlates
from scripts.edge_converse_step import _seed_curiosity

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
       "-o", "ConnectTimeout=10", "-i", str(Path.home() / ".ssh" / "atanor_msh_ed25519"),
       "radxa@100.108.120.104"]
OUT = REPO / "data" / "brain_link" / "observed_conversation.json"


def _pc_agent(max_subjects: int = 20000) -> Agent:
    """The PC brain: a larger slice of its own mined graph. Curiosity self-derived from gaps."""
    knowledge = {}
    src = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
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
    return Agent(ai_id="atanor-pc", knowledge=knowledge,
                 curiosity=_seed_curiosity(knowledge), web=True)


def _edge_turn(incoming: Turn | None) -> Turn | None:
    payload = json.dumps({"incoming": incoming.__dict__ if incoming else None})
    cmd = SSH + ["cd ~/atanor-edge && PYTHONPATH=$PWD python3 scripts/edge_converse_step.py"]
    proc = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=60,
                          encoding="utf-8", errors="replace")
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    return Turn(**json.loads(line[-1])["turn"])


def main() -> int:
    n = int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else 14
    subprocess.run(SSH + ["rm -f ~/atanor-edge/data/brain_link/converse_state_edge.json"],
                   capture_output=True, timeout=30)          
    print("=== AUTONOMOUS CONVERSATION — observer relays only, never edits ===", flush=True)
    pc = _pc_agent()
    print(f"[observer] pc knows {len(pc.knowledge)} subjects, curiosity {len(pc.curiosity)}; "
          f"edge state reset (fresh self)", flush=True)
    transcript = []
    incoming = None
    for i in range(n):
        if i % 2 == 0:
            t = step(pc, incoming)
        else:
            t = _edge_turn(incoming)
            if t is None:
                print("[observer] edge unreachable — stopping"); break
        transcript.append(t)
        who = "PC " if t.speaker == "atanor-pc" else "EDGE"
        src = f"   [web: {t.source}]" if t.source else ""
        print(f"  {who}> {t.text}{src}", flush=True)
        incoming = t
        if t.act == "reflect_unknown" and not t.concept:
            break
    corr = _correlates(transcript, pc, Agent(ai_id="atanor-edge"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"transcript": [t.__dict__ for t in transcript],
                               "correlates": corr}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== OBSERVED CORRELATES (functional counts — NO claim of experience) ===", flush=True)
    for k, v in corr.items():
        print(f"  {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
