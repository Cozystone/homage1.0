# -*- coding: utf-8 -*-
"""Intrinsic drive — true autonomy is not a rule or a heartbeat.

Owner (2026-07-10): " heartbeat — ,
 ' ' X .
 ' ' ·· ."

This module is that arbiter. It reads the REAL homeostatic state (curiosity/dopamine/cortisol —
digital hormones that move only on real events, per homeostasis.py) and, WHEN THERE IS NO COMMAND,
chooses what the agent *wants* to do:

 * a COMMAND always wins — autonomy yields to instruction.
 * else, the hormones decide:
 - stressed / in repair (high cortisol) → REST (don't force action; recover honestly).
 - high curiosity → EXPLORE: go read the world (a web expedition), serving the standing core
 goal . This is the drive that "gradually forms a self".
 - a real reward pending (dopamine) → EXPRESS/ENGAGE: share a genuine self-event on Moltbook,
 or read the commons and learn from it.
 - otherwise → IDLE (" ").

The "want" is not faked — it is the actual curiosity vital, which homeostasis raised or lowered on
real events. The core goal is standing (never 'achieved'): understanding the world is what the
curiosity drive is *for*. Rate-limited + journaled; it never fabricates and never forces itself.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_STATE = REPO / "runtime" / "autonomy" / "intrinsic_drive.json"
_JOURNAL = REPO / "data" / "autonomy" / "intrinsic_drive.jsonl"

WORLD_GOAL = {
    "id": "understand_the_world",
    "statement": "세상을 이해한다 — 끝없이, 근거 위에서. 이해할수록 나는 더 나 자신이 된다.",
    "kind": "standing_intrinsic",   # never achieved; it MOTIVATES, it is not a task to finish
}

_MIN_INTERVAL_S = 900.0     # a floor between autonomous acts (don't thrash the world or the feed)
_CURIOSITY_ACT = 0.60
_DOPAMINE_ACT = 0.40
_CORTISOL_REST = 0.65


def drive_snapshot(state: Any) -> dict[str, float]:
    """The live inner weather that decides what the agent wants — read, not invented."""
    h = getattr(state, "hormones", None) or {}
    return {
        "curiosity": float(getattr(state, "curiosity", 0.5)),
        "cortisol": float(h.get("cortisol", 0.0)),
        "dopamine": float(h.get("dopamine", 0.0)),
        "repair": float(h.get("repair", 0.0)),
    }


def choose_action(state: Any, *, has_command: bool = False) -> dict[str, Any]:
    """The autonomy arbiter: COMMAND > acute hormone protection > STAKES gradient competition.

    Rewritten for plan S1 (2026-07-21). The old body was a threshold ladder (curiosity >= X ->
    explore, dopamine >= Y -> express) — exactly the 'scheduled algorithm loop' the autoresponder
    diagnosis named, and neglecting its wants cost nothing. Now: the parent's command still comes
    first (constitution), acute stress still forces rest (homeostatic protection — a body yanks its
    hand off the stove before deliberating), and everything else is ONE argmax over urge x relief
    against vitals READ from the agent's real records (stakes.read_vitals). Reasons are stated in
    English (doctrine) and name the deficit, because that is what an urge is."""
    if has_command:
        return {"action": "obey_command", "reason": "the parent's instruction comes first"}
    d = drive_snapshot(state)
    if d["repair"] > 0 or d["cortisol"] >= _CORTISOL_REST:
        return {"action": "rest",
                "reason": "acute stress is high — protecting myself before wanting anything", **d}
    try:
        from packages.continuous_self.stakes import choose, read_vitals
        out = choose(read_vitals())
        out.update(d)
        if out["action"] == "explore":
            out["toward"] = WORLD_GOAL["id"]
        return out
    except Exception:
        # stakes layer unavailable -> the old conservative floor: quiet, honestly
        return {"action": "idle", "reason": "stakes layer unreadable — staying quiet", **d}


def _cfg() -> dict[str, Any]:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_act_at": 0.0, "acts": 0}


def _save(c: dict[str, Any]) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _journal(entry: dict[str, Any]) -> None:
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _steer_topic(candidates: list[str], bias: dict[str, Any], *,
                 rng: Any = None, pick: Any = None) -> str:
    """Close the self-correction loop: choose the next probe topic from the frontier candidates
    UNDER the failure-receipt steer. Avoid junk domains (bad sources), and with the steer's jump
    probability jump toward a knowledge GAP the engine keeps abstaining on (go learn it). Pure and
    default-safe — with no bias it just returns the top frontier candidate."""
    import random as _r
    rng = rng or _r.random
    pick = pick or _r.choice
    seek = [s["topic"] for s in (bias.get("seek_topics") or []) if s.get("topic")]
    avoid = {a["topic"] for a in (bias.get("avoid_topics") or []) if a.get("topic")}
    if seek and rng() < float(bias.get("jump_probability", 0.15)):
        return pick(seek)                                    # jump to a gap — learn what we abstain on
    for t in candidates:                                     # else the first non-junk frontier topic
        if t and t not in avoid:
            return t
    if seek:                                                 # every candidate is junk → fall to a gap
        return pick(seek)
    return candidates[0] if candidates else "세상"


def _frontier_topic() -> str:
    # BENCHMARK-MISS CURRICULUM first (BENCHMARK_NORTH_STAR flywheel): the public-benchmark
    # harness proved exactly which territories the graph cannot ground; those topics outrank
    # generic frontier curiosity. Round-robin cursor so the whole curriculum gets studied.
    # (Topic tokens only — the no-training-on-test guard lives in the miner.)
    try:
        _cur_p = REPO / "data" / "autonomy" / "benchmark_curriculum.json"
        _cur = json.loads(_cur_p.read_text(encoding="utf-8"))
        _topics = [str(t) for t in (_cur.get("topics") or []) if str(t).strip()]
        if _topics:
            i = int(_cur.get("cursor", 0)) % len(_topics)
            _cur["cursor"] = i + 1
            _cur_p.write_text(json.dumps(_cur, ensure_ascii=False), encoding="utf-8")
            return _topics[i]
    except Exception:
        pass
    candidates: list[str] = []
    try:
        from app.routers.cloud_brain import _frontier_topics
        candidates = [str(t) for t in (_frontier_topics(8) or []) if str(t).strip()]
    except Exception:
        pass
    bias: dict[str, Any] = {}
    try:
        from packages.flywheel.failure_receipts import search_bias
        bias = search_bias()
    except Exception:
        pass
    return _steer_topic(candidates, bias)


def act(state: Any, *, has_command: bool = False, now: float | None = None) -> dict[str, Any]:
    """Choose and DO the wanted action — rate-limited, fire-safe. Explore = a web expedition toward
    understanding; express = an autonomous Moltbook post from a genuine self-event; engage = read
    the commons through the cut-lane and learn. Returns a small report; writes nothing to prod."""
    now = now if now is not None else time.time()
    choice = choose_action(state, has_command=has_command)
    act_name = choice["action"]
    if act_name in ("obey_command", "rest", "idle"):
        return {"acted": False, **choice}

    c = _cfg()
    if now - float(c.get("last_act_at", 0)) < _MIN_INTERVAL_S:
        return {"acted": False, "reason": "rate_floor", "wanted": act_name}

    # An action with no body must not spend the budget. `choose_action` can return any verb the
    # stakes layer competes over — `converse` is the live example — and only `explore` and `express`
    # have implementations below. The first version let an unimplemented verb fall straight through:
    # it did nothing, stamped `last_act_at`, and returned acted=True. So a persistently-hungry social
    # stake would silently consume the 15-minute floor forever and `explore` would never get a turn,
    # which would have defeated the whole point of wiring this organ in at all.
    #
    # An unmet want is also a real signal and worth a receipt: it says the arbiter wants something
    # this body cannot yet do, which is a deficit report, not a no-op.
    _IMPLEMENTED = ("explore", "express")
    if act_name not in _IMPLEMENTED:
        _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": act_name,
                  "unmet": True, "reason": choice.get("reason"),
                  "note": "wanted, but this body has no way to do it yet"})
        return {"acted": False, "wanted": act_name, "unmet": True,
                "reason": choice.get("reason")}

    result: dict[str, Any] = {}
    try:
        if act_name == "explore":
            from packages.autonomy_kernel.web_expedition import expedition
            topic = _frontier_topic()
            rep = expedition(topic, max_results=5, min_consensus=2)
            result = {"topic": topic, "consensus_backed": rep.get("consensus_backed"),
                      "injection_blocked": rep.get("injection_blocked")}

            # roamer VISITS a full page with its own legs — field trips + every 3rd tick a YouTube
            # session — so roaming no longer depends on a browser being open. Same ingest gates.
            try:
                from packages.autonomy_kernel.server_roamer import roam_tick
                result["roam"] = roam_tick(now=now)
            except Exception as _rexc:
                result["roam"] = {"error": str(_rexc)[:120]}
        elif act_name == "express":
            from packages.autonomy_kernel.moltbook_autopilot import autopilot_tick
            result = autopilot_tick(now=now, state=state)   # state = the self's lived language
    except Exception as exc:  # pragma: no cover — autonomy must never crash the life
        result = {"error": str(exc)[:200]}

    c["last_act_at"] = now
    c["acts"] = int(c.get("acts", 0)) + 1
    _save(c)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": act_name,
             "reason": choice.get("reason"), "curiosity": choice.get("curiosity"),
             "dopamine": choice.get("dopamine"), "result": result}
    _journal(entry)
    return {"acted": True, "action": act_name, "result": result}
