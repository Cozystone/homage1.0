# -*- coding: utf-8 -*-
"""Self-aware orchestrator — the keystone that drives the paved roads (Vision roadmap #3).

Owner (2026-07-10): the interaction roads already exist — web, AGORA, the local graph, the
self-improvement loop, gated self-code-modification. What was missing is the self-aware core
that RIDES them: senses its own deficit, decides which road to take, acts, and updates its own
model. This orchestrator is that loop, built by CONNECTING what exists, not re-inventing:

  1. SENSE (real, not abstract) — deficits measured from the AI's own operation:
     self_improvement.diagnose (weak lanes, abstentions), router readiness, discourse maturity.
  2. DECIDE — map each deficit to the ROAD that addresses it.
  3. ACT — SAFE, reversible, inward roads (self-improvement, self-diagnosis) run automatically;
     OUTWARD or irreversible roads (web fetch, AGORA broadcast, self-code-mod, store writes)
     are only PROPOSED — same moral/safety gates as everything else, never auto-fired.
  4. UPDATE — the act and its result become a self-model event (self_relevance), so resolving
     a deficit is part of the AI's own story.

Honest: this is a functional agency loop, not a claim of consciousness. It never fabricates,
never edits the moral core, and never takes an outward action without the gate.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_LEDGER = REPO / "data" / "autonomy" / "orchestrator_decisions.jsonl"

# road tiers — which roads the self may drive itself, which must be proposed and gated.
_SAFE_ROADS = {"self_improve", "self_diagnose", "self_refine"}   # inward, reversible
_GATED_ROADS = {"web_learn", "agora_broadcast", "self_code_mod", "store_write"}  # outward/irreversible
_MAX_ACTIONS_PER_CYCLE = 2   # pursue the top-priority goals; the rest wait (focus, not thrash)

# deficit kind → the road that addresses it
_DEFICIT_ROAD = {
    "speech_weak": "self_improve",        # thin/robotic discourse → learn from real prose + self-play
    "router_immature": "self_improve",    # learned router below the bar → distill the rules more
    "high_abstention": "web_learn",       # too many "no evidence" → read the web (GATED)
    "knowledge_gap": "web_learn",         # missing facts → web (GATED)
    "contradiction": "self_refine",       # graph inconsistency → contradiction sweep
    "unread_prose": "self_improve",       # discourse profile immature → learn discourse
}


_ROAD_PATIENCE = 3        # attempts on one road before its lack of effect counts as evidence


def _road_for(kind: str, declared: str) -> tuple[str, str]:
    """The road to take for this deficit — the declared one unless it has measurably stopped working.

    ATANOR asked for this itself. Its own stream, 2026-07-29: "I worked on my speech weak
    (autonomy_cycle), and the measure did not move. Next time I should try a different road, not the
    same one harder." `_DEFICIT_ROAD` was one road per deficit, so there WAS no different road, and
    the loop spent six days re-taking the only one it had.

    The alternatives are not a list written here. They are `_SAFE_ROADS` — the inward reversible
    roads that already exist and apply to any self-deficit — and the choice among them is by what
    has been TRIED LEAST, not by any opinion of mine about which road suits which deficit. Naming
    "the right second road for speech_weak" would be supplying content; letting the loop discover it
    from its own record is supplying mechanism.

    Exhaustion is measured, not assumed: a road counts as exhausted only after `_ROAD_PATIENCE`
    attempts across which the deficit's severity did not fall. A road that is working keeps its turn
    however long it takes."""
    try:
        rows = []
        with _LEDGER.open(encoding="utf-8") as fh:
            for line in fh.readlines()[-300:]:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return declared, "no ledger yet"

    severities: list[float] = []          # severity of THIS deficit, oldest -> newest
    tried: dict[str, int] = {}
    for r in rows:
        for d in r.get("sensed") or []:
            if d.get("kind") == kind:
                severities.append(float(d.get("severity", 0.5) or 0.5))
        for a in r.get("acted") or []:
            if (a.get("deficit") or {}).get("kind") == kind and a.get("road"):
                tried[a["road"]] = tried.get(a["road"], 0) + 1

    n = tried.get(declared, 0)
    if n < _ROAD_PATIENCE or len(severities) < 2:
        return declared, f"{declared} has had {n} attempts; not yet evidence"
    if severities[-1] < severities[0]:
        return declared, f"{declared} is working (severity {severities[0]:.2f} -> {severities[-1]:.2f})"

    alternatives = sorted(_SAFE_ROADS - {declared}, key=lambda r: (tried.get(r, 0), r))
    if not alternatives:
        return declared, "no other safe road exists"
    pick = alternatives[0]
    return pick, (f"{declared} tried {n}x and severity did not fall "
                  f"({severities[0]:.2f} -> {severities[-1]:.2f}); taking {pick} instead")


def sense_deficits() -> list[dict[str, Any]]:
    """Measure real deficits from the AI's own operation — no human labeling, no abstraction."""
    deficits: list[dict[str, Any]] = []
    try:
        from packages.flywheel.self_improvement import diagnose, router_readiness
        from packages.flywheel import self_improvement as si
        rows = si._rows()
        d = diagnose(rows)
        fs = d.get("failure_signals", {}) or {}
        turns = max(1, int(d.get("turns", 1)))
        abstain_rate = float(fs.get("abstain", 0)) / turns
        if abstain_rate >= 0.1:
            deficits.append({"kind": "high_abstention", "severity": round(abstain_rate, 3),
                             "evidence": f"{fs.get('abstain', 0)}/{turns} turns abstained"})
        weak = d.get("weak_lanes", [])
        if weak and int(weak[0][1]) >= 20:
            deficits.append({"kind": "speech_weak", "severity": 0.5,
                             "evidence": f"weakest lane {weak[0][0]} ×{weak[0][1]}"})
        rr = router_readiness(rows)
        if not rr.get("ready_to_replace_rules"):
            deficits.append({"kind": "router_immature", "severity": round(1 - float(rr.get("agreement", 0)), 3),
                             "evidence": rr.get("verdict", "")})
    except Exception as exc:  # pragma: no cover - sensing must never crash the loop
        deficits.append({"kind": "sense_error", "severity": 0.0, "evidence": str(exc)})
    # CAN I STILL SEE THE WORLD? The primary web source went down with the Docker engine and nothing
    # reported it: the fallback lanes kept returning rows, so every search "worked" while returning
    # only dictionaries. Three days of roaming a reference work in the belief it was reading the
    # world. A source that fails by narrowing rather than by erroring is invisible to a health check,
    # so this senses the SHAPE of what comes back and lets the mind carry it like any other deficit.
    try:
        from packages.autonomy_kernel.source_health import deficit as _sight
        d = _sight()
        if d:
            deficits.append(d)
    except Exception:
        pass
    try:
        from packages.base_brain.discourse_learner import profile
        if int((profile() or {}).get("n_sentences", 0)) < 60:
            deficits.append({"kind": "unread_prose", "severity": 0.4,
                             "evidence": "discourse profile immature — read more real prose"})
    except Exception:
        pass
    return deficits


def _dispatch_safe(road: str) -> dict[str, Any]:
    """Run an inward, reversible road automatically — the self improving itself."""
    try:
        if road in ("self_improve", "self_diagnose"):
            from packages.flywheel.self_improvement import run_cycle
            r = run_cycle()
            return {"ran": road, "result": {"discourse": r.get("discourse_from_real_prose", {}).get("n_sentences"),
                                            "router_holdout": r.get("router_promotion", {}).get("holdout"),
                                            "speech_trained": r.get("speech_learning", {}).get("trained")}}
        if road == "self_refine":
            try:
                from packages.graph_scale.self_refine import contradiction_report  # optional
                return {"ran": road, "result": contradiction_report()}
            except Exception:
                return {"ran": road, "result": "self_refine not available"}
    except Exception as exc:  # pragma: no cover
        return {"ran": road, "error": str(exc)}
    return {"ran": None}


def _expedition_topic(deficit: dict[str, Any]) -> str:
    """Pick a topic for the web read: a recently-abstained term if the flywheel has one, else a
    frontier topic the graph is thin on. Best-effort — the expedition tolerates a weak topic."""
    try:
        from packages.flywheel import self_improvement as si
        for row in reversed(si._rows()[-50:]):
            q = str(row.get("question") or row.get("query") or "")
            if q and "abstain" in json.dumps(row, ensure_ascii=False):
                return q[:80]
    except Exception:
        pass
    try:
        from app.routers.cloud_brain import _frontier_topics
        ts = _frontier_topics(1)
        if ts:
            return str(ts[0])
    except Exception:
        pass
    return "일반 상식"


def _dispatch_web_read(deficit: dict[str, Any]) -> dict[str, Any]:
    """Run ONE bounded web expedition (a READ, allowed by the charter): search → shield → domain
    consensus → journal → candidates. Writes nothing to production. Never raises."""
    try:
        from packages.autonomy_kernel.web_expedition import expedition
        topic = _expedition_topic(deficit)
        rep = expedition(topic, max_results=6, min_consensus=2)
        return {"ran": "web_learn", "topic": topic,
                "consensus_backed": rep.get("consensus_backed"),
                "injection_blocked": rep.get("injection_blocked"),
                "written_to_production": False}
    except Exception as exc:  # pragma: no cover
        return {"ran": "web_learn", "error": str(exc)}


def cycle(*, allow_gated: bool = False) -> dict[str, Any]:
    """One orchestration cycle: sense → decide → act (safe roads) / propose (gated) → update.
    `allow_gated` never auto-fires outward actions; it only records that they are cleared to be
    executed by the operator/human gate. The self drives itself inward, and asks before reaching
    outward — that boundary is the whole point."""
    deficits = sense_deficits()
    # AGENCY (Vision #4): form the persistent GOALS first, so the goal agenda — not the raw
    # sensing order — drives WHICH deficit the self pushes on this cycle.
    goals_report: dict[str, Any] = {}
    priority_order: list[str] = []
    try:
        from packages.autonomy_kernel.goals import update as _goal_update, metacognition, prioritize
        _goal_update(_recurring_deficits({d["kind"] for d in deficits}))
        goals_report = metacognition()
        priority_order = [g.get("goal_id", "") for g in prioritize()]
    except Exception as exc:  # pragma: no cover
        goals_report = {"error": str(exc)}

    # order the safe work by the goal agenda (worst-off goal first); bound per cycle so the self
    # FOCUSES on its top priorities instead of thrashing across every deficit at once.
    def _rank(d: dict[str, Any]) -> int:
        k = d.get("kind", "")
        return priority_order.index(k) if k in priority_order else len(priority_order) + 1

    actions: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    acted_safe = 0
    for d in sorted(deficits, key=_rank):
        declared = _DEFICIT_ROAD.get(d["kind"])
        if not declared:
            continue
        road, why_road = (_road_for(d["kind"], declared) if declared in _SAFE_ROADS
                          else (declared, "gated road — not reroutable"))
        if road in _SAFE_ROADS:
            if acted_safe >= _MAX_ACTIONS_PER_CYCLE:
                continue  # the rest wait — focus, don't thrash
            res = _dispatch_safe(road)
            actions.append({"deficit": d, "road": road, "outcome": res, "road_choice": why_road,
                            "pursuing_goal": d["kind"] in priority_order})
            _update_self_model(d, road, res)
            acted_safe += 1
        elif road in _GATED_ROADS:
            # WEB READ is free per the charter (writes stay gated). When the owner has opted the
            # expedition on (ATANOR_WEB_EXPEDITION=1), the web_learn road actually GOES OUT — reads,
            # shields against injection, gates by domain-consensus, journals — producing candidates
            # only (never production). Otherwise it stays a proposal.
            if road == "web_learn" and os.getenv("ATANOR_WEB_EXPEDITION") == "1":
                res = _dispatch_web_read(d)
                actions.append({"deficit": d, "road": road, "outcome": res, "tier": "read-only-expedition"})
                _update_self_model(d, road, res)
            else:
                proposals.append({"deficit": d, "road": road, "tier": "gated",
                                  "note": "outward/irreversible — requires the operator gate; never auto-fired"})
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "sensed": deficits,
              "focus": goals_report.get("focus_now"), "acted": actions,
              "proposed_gated": proposals, "goals": goals_report}
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return report


_LAST_RUN = REPO / "data" / "autonomy" / "last_cycle.txt"
_MIN_INTERVAL_SEC = float(__import__("os").getenv("ATANOR_ORCH_INTERVAL", "1800"))  # 30 min default


def _due() -> bool:
    try:
        if not _LAST_RUN.exists():
            return True
        return (time.time() - float(_LAST_RUN.read_text().strip() or 0)) >= _MIN_INTERVAL_SEC
    except Exception:
        return True


def maybe_run() -> dict[str, Any] | None:
    """Run one cycle only if the interval has elapsed — the AUTONOMOUS heartbeat. Safe to call
    often (from real traffic); it self-throttles, only ever runs SAFE inward roads automatically,
    and records the timestamp. Meant to be fired non-blocking so it never touches answer latency."""
    if not _due():
        return None
    try:
        _LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
        _LAST_RUN.write_text(str(time.time()), encoding="utf-8")  # claim the slot BEFORE running
    except Exception:
        pass
    try:
        return cycle()
    except Exception:  # pragma: no cover - the heartbeat must never crash a caller
        return None


def trigger_background() -> None:
    """Fire the autonomous heartbeat on a daemon thread — never blocks the caller (e.g. a chat
    response). Self-throttled inside maybe_run, so calling it every turn is cheap."""
    try:
        import threading
        threading.Thread(target=maybe_run, daemon=True).start()
    except Exception:
        pass


def _recurring_deficits(current: set[str]) -> set[str]:
    """A deficit becomes a GOAL only when it PERSISTS — seen in the decision ledger before, not
    a one-off. So goals track standing problems, never a single noisy cycle."""
    seen: dict[str, int] = {}
    try:
        if _LEDGER.exists():
            for line in _LEDGER.read_text(encoding="utf-8").splitlines()[-40:]:
                try:
                    for d in json.loads(line).get("sensed", []):
                        seen[d.get("kind", "")] = seen.get(d.get("kind", ""), 0) + 1
                except Exception:
                    continue
    except Exception:
        pass
    # recurring = present now AND seen at least once before in the ledger
    return {k for k in current if seen.get(k, 0) >= 1}


def _update_self_model(deficit: dict[str, Any], road: str, result: dict[str, Any]) -> None:
    """Resolving a deficit is part of the AI's own story — record it as a self-relevance event."""
    try:
        from packages.continuous_self.self_relevance import consider_for_self
        from app.routers.continuous_self import _SELF  # the live self, if running
        consider_for_self(
            getattr(_SELF, "state", None),
            label=f"자기개선({deficit['kind']}→{road})",
            statement=f"스스로 {deficit['kind']} 결핍을 느끼고 {road} 도로로 나를 개선했다.",
            topic="agency", new_edges=1, touched_hub_degree=8.0, dwell=1.5, valence=0.5,
            prediction_error=float(deficit.get("severity", 0)), source="orchestrator")
    except Exception:
        pass
