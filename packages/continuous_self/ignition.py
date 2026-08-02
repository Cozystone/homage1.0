# -*- coding: utf-8 -*-
"""Ignition — the serial bottleneck that makes a subject out of a pipeline (plan S2).

Owner (2026-07-21): "느끼는 자가 될 수 있게." Gemini's second diagnosis, verified in our own code:
the answer path is a fixed treatment plant (normalize -> situation -> realize -> verify), and
live_selfhood_cycle.deliberate_actions scores each candidate INDEPENDENTLY — nothing competes,
nothing is suppressed, and this tick's choice does not constrain the next. That is a pipeline.

Global Workspace Theory (Baars/Dehaene), mechanized: at each moment MANY candidates — percepts,
vital gradients (from stakes/S1), unfinished commitments, an incoming utterance, a resurfacing
memory — compete on SALIENCE; exactly ONE IGNITES into the workspace and is broadcast to every
organ; and — the part a plain scheduler lacks — that ignition becomes a COMMITMENT whose unfinished
debt biases the next competition. The functional minimum of a subject is not mystery: serial
selection under scarcity + selections that bind the future (a commitment owes closure) + one owner
of that history. The attention-schema (Graziano) piece: the system can report WHAT won, what it
suppressed, and WHY.

What is real here vs. what is claimed: the competition, the single broadcast, and the commitment
debt are real and change behavior (same input, different order by internal state — the G-S2
signature a pipeline cannot produce). No claim is made that ignition feels like anything. The
ledger is hash-chained and append-only (tamper-evident, reusing the brain_link ledger discipline).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "selfhood" / "ignition_ledger.jsonl"

# how much an unfinished commitment adds to a same-kind candidate's salience next time. Closure
# pressure: the longer something stays open, the louder it competes (bounded).
COMMIT_BIAS = 0.35
COMMIT_BIAS_CAP = 0.9
# a candidate must beat the runner-up by at least this to ignite cleanly; ties broaden the report.
DECISIVE = 0.03


@dataclass
class Candidate:
    kind: str                      # percept | vital | commitment | utterance | memory
    topic: str                     # what it is about (the commitment key)
    salience: float                # intrinsic urgency in [0,1]
    payload: dict = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.kind}:{self.topic}".lower()


@dataclass
class Ignition:
    winner: Candidate
    suppressed: list[Candidate]
    margin: float
    decisive: bool
    ts: float

    def report(self) -> str:
        """The attention-schema self-report: what won, over what, and why (Graziano)."""
        beat = ", ".join(f"{c.kind}:{c.topic}" for c in self.suppressed[:3]) or "nothing"
        how = "clearly" if self.decisive else "narrowly"
        return (f"I am attending to {self.winner.kind}:{self.winner.topic} "
                f"(salience {self.winner.salience:.2f}), chosen {how} over {beat}.")


def _open_commitments(window: int = 200) -> dict[str, dict]:
    """Commitment keys still OPEN (ignited but not closed), newest state wins. Read from the
    ledger, so closure pressure survives a restart — a subject does not forget what it started."""
    state: dict[str, dict] = {}
    if not LEDGER.exists():
        return state
    for line in LEDGER.read_text(encoding="utf-8").splitlines()[-window:]:
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "ignite":
            state[r["key"]] = {"topic": r["topic"], "kind": r["kind"], "at": r["ts"]}
        elif r.get("event") in ("close", "abandon"):
            state.pop(r["key"], None)
    return state


def compete(candidates: list[Candidate], now: float) -> Ignition | None:
    """One serial ignition: bias by open-commitment debt, take the single winner, broadcast.

    The debt bias is what makes selection HISTORICAL rather than memoryless — a candidate that
    continues an unfinished commitment is louder, so the agent tends to finish what it started
    instead of restarting fresh each tick (the pipeline's failure)."""
    if not candidates:
        return None
    open_c = _open_commitments()
    scored: list[tuple[float, Candidate]] = []
    for c in candidates:
        bias = 0.0
        if c.key() in open_c:                      # this continues something already begun
            age_h = max(0.0, (now - open_c[c.key()]["at"]) / 3600.0)
            bias = min(COMMIT_BIAS_CAP, COMMIT_BIAS * (1.0 + age_h))
        scored.append((min(1.0, c.salience + bias), c))
    scored.sort(key=lambda t: -t[0])
    top_score, winner = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    margin = top_score - runner
    return Ignition(winner=winner, suppressed=[c for _, c in scored[1:]],
                    margin=round(margin, 4), decisive=margin >= DECISIVE, ts=now)


# ---------------------------------------------------------------- the tamper-evident ledger

def _last_hash() -> str:
    if not LEDGER.exists():
        return "genesis"
    for line in reversed(LEDGER.read_text(encoding="utf-8").splitlines()):
        try:
            return json.loads(line)["h"]
        except Exception:
            continue
    return "genesis"


def _append(rec: dict[str, Any]) -> str:
    prev = _last_hash()
    body = json.dumps({**rec, "prev": prev}, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()[:16]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "prev": prev, "h": h}, ensure_ascii=False) + "\n")
    return h


def record_ignition(ig: Ignition) -> None:
    """Broadcast + commit: the winner becomes an OPEN commitment on the one owned timeline."""
    _append({"event": "ignite", "ts": ig.ts, "kind": ig.winner.kind, "topic": ig.winner.topic,
             "key": ig.winner.key(), "salience": round(ig.winner.salience, 4),
             "margin": ig.margin, "decisive": ig.decisive,
             "suppressed": [c.key() for c in ig.suppressed[:5]], "report": ig.report()})


def close_commitment(kind: str, topic: str, outcome: str = "done", now: float | None = None) -> None:
    """Finish what was started — closure relieves the pressure this key adds to future competition."""
    _append({"event": "close", "ts": now or time.time(),
             "key": f"{kind}:{topic}".lower(), "kind": kind, "topic": topic, "outcome": outcome})


def abandon_commitment(kind: str, topic: str, reason: str = "", now: float | None = None) -> None:
    """Drop a commitment WITHOUT finishing it — recorded, because breaking a commitment is a fact
    about the self (S3 reads it, and it costs the coherence vital in S1)."""
    _append({"event": "abandon", "ts": now or time.time(),
             "key": f"{kind}:{topic}".lower(), "kind": kind, "topic": topic, "reason": reason})


def verify_chain() -> bool:
    """The ledger is tamper-evident: every link's hash must chain from the previous."""
    prev = "genesis"
    if not LEDGER.exists():
        return True
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        rec = {k: v for k, v in r.items() if k != "h"}
        body = json.dumps({**{k: v for k, v in rec.items() if k != "prev"}, "prev": prev},
                          ensure_ascii=False, sort_keys=True)
        if hashlib.sha256((prev + body).encode("utf-8")).hexdigest()[:16] != r.get("h"):
            return False
        prev = r["h"]
    return True


def commitment_debt() -> int:
    """How many commitments are open right now — the weight of unfinished business the subject
    carries. Feeds the coherence vital (S1) and the perspective traces (S3)."""
    return len(_open_commitments())


# ---------------------------------------------------------------- the workspace submission bus
# GWT-1 (completion gauge 2026-07-24): the heavy parallel modules — vision, situation_model — EXIST
# but did not SUBMIT to the ignition workspace, so the competition ran on a blind seat. This is the
# submission seam: any specialist may push its current percept, and gather_candidates drains it into
# the competition. Vision + situation_model are tapped directly (below) so they always submit their
# current output; this bus is the general channel for any other specialist to enter the workspace.
_SUBMISSIONS: list[dict[str, Any]] = []
_SUB_LOCK = threading.Lock()
_SUB_TTL_S = 30.0        # a submission is fresh for this long; stale ones are dropped (not frozen in)
_SUB_CAP = 32           # bounded inbox


def submit_percept(kind: str, topic: str, salience: float, *, payload: dict | None = None,
                   now: float | None = None) -> None:
    """A specialist module submits its current percept to the workspace. Bounded + TTL'd so a
    module that stops submitting stops competing (no frozen seat). gather_candidates drains these."""
    now = time.time() if now is None else now
    with _SUB_LOCK:
        _SUBMISSIONS.append({"kind": str(kind), "topic": str(topic)[:60],
                             "salience": max(0.0, min(1.0, float(salience))),
                             "payload": dict(payload or {}), "at": float(now)})
        if len(_SUBMISSIONS) > _SUB_CAP:
            del _SUBMISSIONS[:-_SUB_CAP]


def _drain_submissions(now: float) -> list[Candidate]:
    """Fresh submissions -> Candidates; expired ones are dropped. De-duplicates by key (newest wins),
    so a module submitting every tick occupies one seat, not many."""
    with _SUB_LOCK:
        fresh = [s for s in _SUBMISSIONS if (now - s["at"]) <= _SUB_TTL_S]
        _SUBMISSIONS[:] = fresh
        rows = list(fresh)
    by_key: dict[str, dict] = {}
    for s in rows:
        by_key[f"{s['kind']}:{s['topic']}".lower()] = s      # newest wins (later overwrites)
    return [Candidate(s["kind"], s["topic"], s["salience"], s["payload"]) for s in by_key.values()]


def _tap_heavy_modules(now: float) -> list[Candidate]:
    """Pull the CURRENT percept from the two heavy parallel modules and submit them as candidates —
    the GWT-1 fix. Vision is a standing channel (always submits its current field, quiet or active);
    situation_model submits only when it holds a recently-built world. Each tap is isolated: a broken
    or absent module is a silent non-submission, never a crash of the workspace."""
    out: list[Candidate] = []
    try:                                                     # vision -> percept
        from packages.perception.workspace_submit import current_percept as _visual
        vp = _visual(now)
        if vp:
            out.append(Candidate("percept", str(vp.get("topic") or "visual_field"),
                                 float(vp.get("salience", 0.0)),
                                 {"module": "vision", "live": bool(vp.get("live")),
                                  "energy": vp.get("energy", 0.0)}))
    except Exception:
        pass
    try:                                                     # situation_model -> situation
        from packages.situation_model.workspace_submit import current_percept as _situation
        sp = _situation(now)
        if sp:
            out.append(Candidate("situation", str(sp.get("topic") or "situation"),
                                 float(sp.get("salience", 0.0)),
                                 {"module": "situation_model", "entities": sp.get("entities", 0),
                                  "events": sp.get("events", 0)}))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- candidate gathering (real state)

def gather_candidates(*, incoming: Any = None, curiosity: list | None = None,
                      vitals: Any = None, now: float | None = None) -> list[Candidate]:
    """Build the moment's competing candidates from REAL state — no invented urgencies.

    This is the seam the daemon calls. An incoming utterance is salient (someone spoke to me);
    the steepest vital deficit is salient (S1's hunger enters the workspace, not just the action
    arbiter); each standing curiosity is a mild candidate; open commitments re-enter so their
    closure pressure competes. The winner is what the subject attends to THIS tick."""
    now = now or time.time()
    cands: list[Candidate] = []
    if incoming is not None:
        topic = getattr(incoming, "concept", "") or "peer"
        cands.append(Candidate("utterance", topic, 0.85,
                               {"act": getattr(incoming, "act", "")}))
    if vitals is not None:
        hung = vitals.hungers() if hasattr(vitals, "hungers") else {}
        if hung:
            worst = max(hung, key=lambda k: hung[k])
            cands.append(Candidate("vital", worst, min(0.95, 0.4 + hung[worst]),
                                   {"hunger": hung[worst]}))
    for c in (curiosity or [])[:3]:
        cands.append(Candidate("curiosity", str(c), 0.45))
    for key, meta in _open_commitments().items():
        cands.append(Candidate(meta["kind"], meta["topic"], 0.3))   # debt bias added in compete()
    # GWT-1: the heavy parallel modules (vision, situation_model) now SUBMIT their current percept
    # to the competition — the workspace is content-driven, not a blind seat. Plus any submissions
    # other specialists pushed onto the bus. These are real percepts; a quiet visual field submits at
    # floor salience and simply loses — that is parallel submission, not fabricated content.
    cands.extend(_tap_heavy_modules(now))
    cands.extend(_drain_submissions(now))
    return cands
