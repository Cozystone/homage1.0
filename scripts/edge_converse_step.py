# -*- coding: utf-8 -*-
"""One conversation turn for the EDGE agent, run ON the Radxa. Stateful across calls via a JSON
state file — the edge agent genuinely lives here: its knowledge slice, its curiosity (self-derived
from its own knowledge gaps), and its OWN web access from this box.

stdin:  {"incoming": <Turn dict> | null}
stdout: {"turn": <Turn dict>}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.brain_link.conversation import Agent, Turn, step

STATE = REPO / "data" / "brain_link" / "converse_state_edge.json"
SLICE = REPO / "data" / "brain_link" / "edge_knowledge_slice.jsonl"


def _seed_curiosity(knowledge: dict, cap: int = 12) -> list[str]:
    """The agent's interests are ITS OWN knowledge gaps: object terms in its bones that it cannot
    itself explain (no subject entry). Self-derived and deterministic — no one picks its topics."""
    gaps: list[str] = []
    seen = set()
    for bones in knowledge.values():
        if not isinstance(bones, list):
            continue
        for b in bones:
            o = str(b[2]).strip()
            k = o.lower()
            if (2 < len(o) < 30 and k not in knowledge and k not in seen
                    and o.replace(" ", "").isalpha()):
                seen.add(k)
                gaps.append(o)
            if len(gaps) >= cap:
                return gaps
    return gaps


def _load_agent() -> Agent:
    if STATE.exists():
        d = json.loads(STATE.read_text(encoding="utf-8"))
        a = Agent(ai_id=d["ai_id"], knowledge=d["knowledge"], curiosity=d["curiosity"],
                  web=True, learned=d["learned"])
        a._asked = set(d["asked"])
        return a
    knowledge: dict = {}
    if SLICE.exists():
        for line in SLICE.open(encoding="utf-8"):
            r = json.loads(line)
            knowledge[r["subject"].lower()] = r["bones"]
    return Agent(ai_id="atanor-edge", knowledge=knowledge,
                 curiosity=_seed_curiosity(knowledge), web=True)


def _save_agent(a: Agent) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "ai_id": a.ai_id, "knowledge": a.knowledge, "curiosity": a.curiosity,
        "learned": a.learned, "asked": sorted(a._asked),
    }, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    inc = payload.get("incoming")
    incoming = Turn(**inc) if inc else None
    agent = _load_agent()
    turn = step(agent, incoming)
    _save_agent(agent)
    print(json.dumps({"turn": turn.__dict__}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
