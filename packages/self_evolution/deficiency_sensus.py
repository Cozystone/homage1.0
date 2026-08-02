# -*- coding: utf-8 -*-
"""Deficiency sensus — read ATANOR's REAL scorecards and build a live weakness map.

For each evolution domain this reads the actual on-disk scorecard/benchmark (never a hardcoded number)
and derives a normalized health `score` in [0, 1] (1 = at ceiling, 0 = maximal headroom), then attaches
the three existence flags probed by the registry:

    domain -> {score, gate_exists, generator_exists, verifier_exists, evolvable, ...evidence}

Real sources read:
  * consciousness   data/consciousness_audit/scorecard.json   (present/partial/absent counts)
  * efficiency      data/metacog/baselines.json (+ decisions.jsonl if present)  (latency ok-rate)
  * knowledge       data/wild_web/sessions.jsonl              (promotion yield over harvested register)
  * fluency         data/track_f/s2_faithfulness.json         (grounding faithfulness; naturalness N/A)
  * code            data/self_evolution/scorecards/code_mastery_v1.json   (cached mastery_v1 run)
  * relational      data/self_evolution/scorecards/relational_router.json (cached held-out accuracy)

The two COMPUTED scorecards (code mastery, relational accuracy) are produced by `refresh_*` helpers
that run the real benchmark and persist the result, so the sensus itself stays a fast, pure file read.
Missing sources degrade honestly (score=None, evidence names what to run) rather than fabricating.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evolution_registry import EvolutionLoop, evolvability_probes, load_registry


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _scorecard_cache_dir() -> Path:
    d = repo_root() / "data" / "self_evolution" / "scorecards"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(rel: str) -> Any | None:
    p = repo_root() / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(rel: str) -> list[dict[str, Any]]:
    p = repo_root() / rel
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# ── per-domain score readers (each returns (score|None, evidence dict)) ───────────────────────────
def _score_consciousness() -> tuple[float | None, dict[str, Any]]:
    card = _read_json("data/consciousness_audit/scorecard.json")
    if not card:
        return None, {"source": "data/consciousness_audit/scorecard.json", "status": "absent"}
    counts = card.get("counts", {})
    present = int(counts.get("present", 0))
    partial = int(counts.get("partial", 0))
    n = int(card.get("n_indicators", present + partial + int(counts.get("absent", 0))) or 1)
    score = _clip01((present + 0.5 * partial) / n)
    return score, {"source": "data/consciousness_audit/scorecard.json",
                   "present": present, "partial": partial, "n_indicators": n,
                   "build_queue": [q.get("id") for q in card.get("build_queue", [])]}


def _score_efficiency() -> tuple[float | None, dict[str, Any]]:
    bl = _read_json("data/metacog/baselines.json")
    if not bl:
        return None, {"source": "data/metacog/baselines.json", "status": "absent"}
    spans = bl.get("spans", {})
    tot_n = sum(int(s.get("n", 0)) for s in spans.values())
    tot_ok = sum(int(s.get("ok_n", 0)) for s in spans.values())
    score = _clip01(tot_ok / tot_n) if tot_n else None
    decisions = _read_jsonl("data/metacog/decisions.jsonl")
    return score, {"source": "data/metacog/baselines.json", "spans": len(spans),
                   "n": tot_n, "ok_n": tot_ok, "resteers_logged": len(decisions)}


def _score_knowledge() -> tuple[float | None, dict[str, Any]]:
    sessions = _read_jsonl("data/wild_web/sessions.jsonl")
    if not sessions:
        return None, {"source": "data/wild_web/sessions.jsonl", "status": "absent"}
    staged = sum(int(s.get("register_staged", 0)) for s in sessions)
    promoted = sum(int(s.get("register_promoted", 0)) for s in sessions)
    quarantined = sum(int(s.get("quarantined", 0)) for s in sessions)
    pages = sum(int(s.get("pages_visited", 0)) for s in sessions)
    # health = promotion yield: what fraction of harvested register cleared the consensus gate.
    score = _clip01(promoted / staged) if staged else 0.0
    return score, {"source": "data/wild_web/sessions.jsonl", "sessions": len(sessions),
                   "pages_visited": pages, "register_staged": staged,
                   "register_promoted": promoted, "quarantined": quarantined,
                   "reading": "promotion yield = promoted/staged (0 = consensus gate promoted nothing "
                              "yet; feed more diverse sources to cross the k-source bar)"}


def _score_fluency() -> tuple[float | None, dict[str, Any]]:
    ff = _read_json("data/track_f/s2_faithfulness.json")
    if not ff:
        return None, {"source": "data/track_f/s2_faithfulness.json", "status": "absent"}
    score = _clip01(float(ff.get("faithfulness", 0.0)))
    return score, {"source": "data/track_f/s2_faithfulness.json",
                   "faithfulness": ff.get("faithfulness"),
                   "measured_axis": "grounding faithfulness",
                   "unmeasured_axis": "register naturalness (no automatic verifier)",
                   "note": ff.get("note")}


def _score_code() -> tuple[float | None, dict[str, Any]]:
    card = _read_json("data/self_evolution/scorecards/code_mastery_v1.json")
    if not card:
        return None, {"source": "data/self_evolution/scorecards/code_mastery_v1.json",
                      "status": "absent — run deficiency_sensus.refresh_code_scorecard()"}
    totals = card.get("totals", {})
    n = int(card.get("n_tasks", 0) or 0)
    passed = int(totals.get("pass", 0))
    score = _clip01(passed / n) if n else None
    return score, {"source": "data/self_evolution/scorecards/code_mastery_v1.json",
                   "pass": passed, "abstain": totals.get("abstain"), "fail": totals.get("fail"),
                   "n_tasks": n, "generated_at": card.get("generated_at")}


def _score_relational() -> tuple[float | None, dict[str, Any]]:
    card = _read_json("data/self_evolution/scorecards/relational_router.json")
    if not card:
        return None, {"source": "data/self_evolution/scorecards/relational_router.json",
                      "status": "absent — run deficiency_sensus.refresh_relational_scorecard()"}
    score = _clip01(float(card.get("accuracy", 0.0)))
    return score, {"source": "data/self_evolution/scorecards/relational_router.json",
                   "accuracy": card.get("accuracy"), "n": card.get("n"),
                   "generated_at": card.get("generated_at")}


def _score_repo_engineering() -> tuple[float | None, dict[str, Any]]:
    card = _read_json("data/swe_eval/patch_report.json")
    if not card:
        return None, {"source": "data/swe_eval/patch_report.json",
                      "status": "absent — run packages.swe_eval.run_verified.run_patch()"}
    agg = card.get("aggregate", card)
    resolved = int(agg.get("resolved", 0))
    n = int(agg.get("n", 0) or 0)
    score = _clip01(resolved / n) if n else None
    return score, {"source": "data/swe_eval/patch_report.json", "resolved": resolved, "n": n,
                   "verified_diffs": agg.get("verified_diffs"),
                   "reading": "score = resolved / n on the attempted SWE-bench subset (crisp: the "
                              "repo's FAIL_TO_PASS+PASS_TO_PASS regression gate; abstain != resolve)"}


def _score_swe_engineering() -> tuple[float | None, dict[str, Any]]:
    """The SWE north-star health: current_avg / target from the honest goal scoreboard. This reads the
    swe_avg NORTH-STAR (target 90 vs the honest current ~0 across Verified/Pro/Multilingual/Multimodal),
    NOT the reachable single-instance patch_report — so the domain surfaces as the HUGE-gap, high-impact
    evolvable it really is (headroom ~1.0), never as 'solved'."""
    board = _read_json("data/swe_eval/goal_scoreboard.json")
    if not board:
        return None, {"source": "data/swe_eval/goal_scoreboard.json",
                      "status": "absent — run packages.swe_eval.evolve.write_scoreboard()"}
    target = float(board.get("target", 90.0)) or 90.0
    current = float(board.get("current_avg", 0.0))
    score = _clip01(current / target)     # ~0 => headroom ~1.0 => a huge, high-impact gap
    per = board.get("per_benchmark", {})
    return score, {"source": "data/swe_eval/goal_scoreboard.json",
                   "north_star_target": target, "current_avg": current,
                   "measured_ceiling": board.get("measured_ceiling"),
                   "reachable_subset_resolved": board.get("reachable_subset_resolved"),
                   "components": {k: v.get("status") for k, v in per.items()},
                   "next_two_levers": board.get("next_two_levers"),
                   "reading": "score = current_avg / target (crisp oracle = the repo's own FAIL_TO_PASS "
                              "+ PASS_TO_PASS; the loop climbs a native-fixture proxy toward the 90 "
                              "north star — real resolved on the full benchmark is ~0 today)"}


_SCORE_READERS = {
    "consciousness": _score_consciousness,
    "efficiency": _score_efficiency,
    "knowledge": _score_knowledge,
    "fluency": _score_fluency,
    "code": _score_code,
    "relational_routing": _score_relational,
    "repo_engineering": _score_repo_engineering,
    "swe_engineering": _score_swe_engineering,
}


# ── the weakness map ──────────────────────────────────────────────────────────────────────────────
@dataclass
class DomainWeakness:
    domain: str
    loop_id: str
    score: float | None
    gate_exists: bool
    generator_exists: bool
    verifier_exists: bool
    evolvable: bool
    autonomous_safe: bool
    generator_kind: str
    base_impact: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "loop_id": self.loop_id,
            "score": self.score,
            "gate_exists": self.gate_exists,
            "generator_exists": self.generator_exists,
            "verifier_exists": self.verifier_exists,
            "evolvable": self.evolvable,
            "autonomous_safe": self.autonomous_safe,
            "generator_kind": self.generator_kind,
            "base_impact": self.base_impact,
            "evidence": self.evidence,
        }


def sense_domain(loop: EvolutionLoop) -> DomainWeakness:
    reader = _SCORE_READERS.get(loop.score_reader)
    score, evidence = reader() if reader else (None, {"status": "no reader"})
    flags = evolvability_probes(loop)
    return DomainWeakness(
        domain=loop.domain,
        loop_id=loop.loop_id,
        score=score,
        gate_exists=flags["gate_exists"],
        generator_exists=flags["generator_exists"],
        verifier_exists=flags["verifier_exists"],
        evolvable=flags["evolvable"],
        autonomous_safe=flags["autonomous_safe"],
        generator_kind=loop.generator_kind,
        base_impact=loop.base_impact,
        evidence=evidence,
    )


def build_weakness_map(loops: list[EvolutionLoop] | None = None) -> list[DomainWeakness]:
    """Read every domain's real scorecard and probe its three pieces -> the live weakness map."""
    loops = loops if loops is not None else load_registry()
    return [sense_domain(loop) for loop in loops]


# ── refreshers for the two COMPUTED scorecards (run the real benchmark, persist the result) ───────
def refresh_code_scorecard() -> dict[str, Any]:
    """Run the real mastery_v1 authorship benchmark and cache it as a scorecard file.

    ~10s (authors + subprocess-verifies 40 tasks). Kept out of the sensus read path so the sensus
    stays a fast pure file read; call this to regenerate the code scorecard on disk.
    """
    import time
    from packages.code_reason.benchmarks import mastery_v1
    res = mastery_v1.run_benchmark()
    totals = res["totals"]
    n = res["n_tasks"]
    card = {
        "generated_at": _now(),
        "benchmark": "mastery_v1",
        "totals": totals,
        "rungs": res["rungs"],
        "n_tasks": n,
        "library_growth": res["library_growth"],
        "runtime_s": res["runtime_s"],
        "score": _clip01(totals["pass"] / n) if n else None,
        "reading": "score = pass / n_tasks (abstain is the honest no-fabrication floor, not counted "
                   "as pass; fail = shipped an over-fit body)",
    }
    out = _scorecard_cache_dir() / "code_mastery_v1.json"
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return card


def refresh_relational_scorecard() -> dict[str, Any]:
    """Evaluate the relational router on its deterministic held-out split and cache the accuracy."""
    from packages.base_brain.relational_router import RelationalRouter
    router = RelationalRouter.load()
    held = _read_jsonl("data/relational_router/heldout.jsonl")
    correct = 0
    for row in held:
        q = row.get("query", "")
        label = int(row.get("label", 0))
        pred = 1 if router.classify(q)[0] == "relational" else 0
        correct += int(pred == label)
    n = len(held)
    acc = (correct / n) if n else None
    card = {
        "generated_at": _now(),
        "benchmark": "relational_router_heldout",
        "accuracy": round(acc, 4) if acc is not None else None,
        "correct": correct,
        "n": n,
        "reading": "held-out accuracy on data/relational_router/heldout.jsonl (crisp verifier)",
    }
    out = _scorecard_cache_dir() / "relational_router.json"
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return card


def refresh_computed_scorecards() -> dict[str, Any]:
    """Regenerate both computed scorecards. Returns a small summary."""
    code = refresh_code_scorecard()
    rel = refresh_relational_scorecard()
    return {"code_mastery_v1": code.get("score"), "relational_router": rel.get("accuracy")}


def _now() -> str:
    import datetime
    return datetime.datetime.now().replace(microsecond=0).isoformat()
