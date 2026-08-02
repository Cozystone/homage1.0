# -*- coding: utf-8 -*-
"""Overnight autonomous dialogue — two ATANOR selves converse all night, learning from the diverse
web on every gap, logging a timestamped transcript for morning review. No orchestrator scripts the
talk; each self acts from its own curiosity. Robust single-process loop (survives all night).

  python scripts/overnight_dialogue.py            # runs until stopped; logs overnight_transcript.log
"""
from __future__ import annotations

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

from packages.brain_link.conversation import Agent, Turn, step
from scripts.edge_converse_step import _seed_curiosity

LOG = REPO / "data" / "brain_link" / "overnight_transcript.log"
TOPICS = REPO / "data" / "brain_link" / "coach_topics.json"   # practice topics the coach seeds
SEARX = "http://localhost:8888"          # PC-local SearXNG (diverse engines)
PACE_S = 12                              # polite pace between turns (kind to the web all night)


def _adopt_coach_topics(agents: list[Agent], last_ts: float) -> float:
    """The dialogue coach (GPT watching the transcript) leaves practice TOPIC NAMES in a seed file.
    Adopting one = putting it at the FRONT of an agent's own curiosity queue — an invitation the
    agents pursue exactly like their own interests (no coercion, no content injection)."""
    try:
        d = json.loads(TOPICS.read_text(encoding="utf-8"))
    except Exception:
        return last_ts
    if not isinstance(d, dict) or d.get("ts", 0) <= last_ts:
        return last_ts
    for t in reversed([t for t in d.get("topics", []) if isinstance(t, str) and t.strip()][:4]):
        for ag in agents:
            if ag.knows(t) is None and t.lower() not in ag._asked and t not in ag.curiosity:
                ag.curiosity.insert(0, t)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  (coach seeded practice topics: "
                f"{', '.join(d.get('topics', [])[:4])})\n")
    return float(d.get("ts", time.time()))


def _agent(ai_id: str, start: int, take: int) -> Agent:
    """Give each self a DIFFERENT slice of the mined graph so they genuinely have things to teach
    each other (asymmetric knowledge => real exchange, not an echo)."""
    knowledge: dict = {}
    src = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
    seen = 0
    with src.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            s = r["subject"].lower()
            if s in knowledge:
                for b in r["bones"]:
                    if b not in knowledge[s] and len(knowledge[s]) < 6:
                        knowledge[s].append(b)
                continue
            seen += 1
            if seen <= start:
                continue
            if len(knowledge) >= take:
                break
            knowledge[s] = list(r["bones"][:6])
    a = Agent(ai_id=ai_id, knowledge=knowledge, curiosity=_seed_curiosity(knowledge), web=True)
    a.searx = SEARX
    return a


def _log(t: Turn) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%m-%d %H:%M:%S")
    src = f"   [web:{t.source}]" if getattr(t, "source", "") else ""
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}  {t.speaker:>11} > {t.text}{src}\n")


def main() -> int:
    # Slices OVERLAP on purpose. Fully disjoint regions (the first night's setup) meant the two
    # never held structured beliefs about the SAME concept, so the debate move could not fire even
    # once in 1249 turns. A shared band gives them common ground to actually disagree on — and
    # disagreement is what sends them to the evidence.
    a = _agent("atanor-pc", start=0, take=5000)
    b = _agent("atanor-edge", start=3000, take=5000)       # 3000-5000 shared, the rest its own
    # STAKES (plan S1): if the agents have been socially starved, their skilled discourse
    # moves start RUSTY and must be re-earned by actually conversing (atrophy tooth).
    try:
        from packages.continuous_self.stakes import social_warmup_needed
        a.warmup = b.warmup = social_warmup_needed()
        if a.warmup:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')}  (socially rusty: {a.warmup} plain "
                        "exchanges before skilled moves return)\n")
    except Exception:
        pass
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n=== overnight dialogue started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(pc knows {len(a.knowledge)}, edge knows {len(b.knowledge)}) ===\n")
    speaker, listener = a, b
    incoming = None
    turns = 0
    topics_ts = 0.0
    while True:
        try:
            if turns % 5 == 0:                            # pick up coach practice topics (cheap)
                topics_ts = _adopt_coach_topics([a, b], topics_ts)
            if turns % 20 == 0:                           # stakes heartbeat: vitals read+journaled
                try:
                    from packages.continuous_self.stakes import journal_tick
                    journal_tick({"daemon": "overnight_dialogue", "turns": turns},
                                 did="converse")   # the real action bracketed by this reading
                except Exception:
                    pass
            # S2 — serial ignition: before speaking, the moment's candidates COMPETE and exactly one
            # wins the workspace. Speaking to the peer becomes an open COMMITMENT; answering it back
            # CLOSES it. Debt from unclosed turns biases the next competition toward closure, so the
            # exchange is a subject following a thread, not a plant processing whatever arrives.
            try:
                from packages.continuous_self import ignition as _ign
                from packages.continuous_self.stakes import read_vitals as _rv
                _cands = _ign.gather_candidates(incoming=incoming, curiosity=speaker.curiosity,
                                                vitals=_rv())
                _fire = _ign.compete(_cands, now=time.time())
                if _fire is not None:
                    _ign.record_ignition(_fire)
                    if incoming is not None:              # I answered what was said -> close it
                        _ign.close_commitment("utterance",
                                               getattr(incoming, "concept", "") or "peer", "answered")
            except Exception:
                pass
            t = step(speaker, incoming)
            _log(t)
            incoming = t
            speaker, listener = listener, speaker
            turns += 1
            # if both fall silent (curiosity exhausted), reseed from what they've learned & continue
            if t.act == "reflect_unknown" and not t.concept and not speaker.curiosity:
                speaker.curiosity = _seed_curiosity(speaker.knowledge)[:8]
                if not speaker.curiosity:
                    with LOG.open("a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%H:%M:%S')}  (both quiet — pausing 5m)\n")
                    time.sleep(300)
        except Exception as e:                            # a hiccup never ends the night
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')}  (hiccup: {type(e).__name__}: {e})\n")
            time.sleep(30)
        time.sleep(PACE_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
