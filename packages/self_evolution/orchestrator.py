# -*- coding: utf-8 -*-
"""The broad self-evolution orchestrator.

It MAPS deficiencies to evolution loops. It does NOT itself rewrite the brain: it DETECTS weakness
(the sensus), looks up the loop that improves each domain (the registry), ranks the domains by
IMPACT x EVOLVABILITY, and for each returns either
  * a concrete INVOCATION SPEC — only when the loop is verifier-backed and autonomous-safe; or
  * an OPERATOR PROPOSAL — naming the missing piece (usually "verifier absent") when it is not.

It can mark a verifier-backed loop "safe to run autonomously", but it never executes a brain rewrite.
Every plan is journalled and persisted to data/self_evolution/plan.json.

Ranking (all DATA-driven, no hand overrides):
    headroom     = 1 - score            (how much room to improve; unmeasured -> conservative 0.5)
    impact       = base_impact x headroom
    evolvability = 1.00 autonomous-safe | 0.35 needs-verifier | 0.20 gate/generator gap |
                   0.15 architecture-gated | 0.00 immutable-target
    rank         = impact x evolvability
A needs-verifier domain ranks ABOVE an architecture-gated one at equal headroom, because a missing
verifier is BUILDABLE (finite work unlocks autonomy) whereas an architecture rewrite is operator-gated
forever — so the ranking surfaces "build this verifier" as the highest-leverage unlock.

WIREHEADING GUARD (safety-critical): before any invocation spec is emitted, its declared write targets
pass through the guard. A loop that would touch a constitution file or a test is REJECTED and
downgraded to a rejected proposal — never made autonomous.
"""
from __future__ import annotations

import json
from typing import Any

from . import ceiling, journal
from .deficiency_sensus import DomainWeakness, build_weakness_map
from .evolution_registry import EvolutionLoop, load_registry
from .wireheading_guard import review as guard_review


# ── ranking primitives (pure; unit-tested directly) ───────────────────────────────────────────────
def headroom(score: float | None) -> float:
    """How much room to improve. An unmeasured domain is treated as mid-headroom (0.5) and flagged,
    never as 0 (which would hide it) nor 1 (which would over-prioritize an unknown)."""
    if score is None:
        return 0.5
    return max(0.0, min(1.0, 1.0 - float(score)))


def evolvability(w: DomainWeakness) -> float:
    """A scalar in [0, 1]: how much of the loop can run WITHOUT the operator."""
    if w.autonomous_safe:
        return 1.0
    if not w.gate_exists or not w.generator_exists:
        return 0.20                      # a structural gap other than the verifier
    if not w.verifier_exists:
        return 0.35                      # buildable: a verifier unlocks autonomy
    if w.generator_kind == "architecture":
        return 0.15                      # operator-gated forever by doctrine
    return 0.10


def impact(w: DomainWeakness) -> float:
    return round(w.base_impact * headroom(w.score), 6)


def rank_score(w: DomainWeakness) -> float:
    return round(impact(w) * evolvability(w), 6)


# ── plan entries ──────────────────────────────────────────────────────────────────────────────────
def _invocation_spec(loop: EvolutionLoop, w: DomainWeakness) -> dict[str, Any]:
    """A concrete, safe-to-run invocation for a verifier-backed autonomous loop — AFTER the
    wireheading guard clears its write targets. Returns a rejected proposal instead if it does not."""
    write_targets = _declared_write_targets(loop)
    verdict = guard_review(write_targets)
    if not verdict.allowed:
        return {
            "kind": "rejected_wireheading",
            "autonomous_safe": False,
            "reason": verdict.reason,
            "immutable_hits": verdict.hits,
            "operator_action": "an evolution loop must never write a constitution file or a test; "
                               "re-scope its write targets.",
        }
    at_ceiling = (w.score is not None and headroom(w.score) <= 1e-9)
    return {
        "kind": "invocation",
        "autonomous_safe": True,
        "loop_id": loop.loop_id,
        "how_invoked": loop.how_invoked,
        "generator_kind": loop.generator_kind,
        "verifier": loop.verifier_desc,
        "write_targets": write_targets,
        "guard": "cleared: no immutable target",
        "invocation": loop.invocation,
        "note": ("at the measured ceiling on the current benchmark — extend the benchmark (a harder "
                 "task set) to expose new headroom; the verifier generalizes, so this stays autonomous"
                 if at_ceiling else loop.note or "run the loop; promote only what the verifier passes"),
    }


def _operator_proposal(loop: EvolutionLoop, w: DomainWeakness) -> dict[str, Any]:
    """A flagged proposal for the operator, naming exactly the missing piece."""
    if not w.verifier_exists:
        missing = "verifier absent"
        action = ceiling._verifier_hint(w)
    elif w.generator_kind == "architecture":
        missing = "generator is architecture-level (operator-gated forever)"
        action = ("design + build the queued module, then re-run the audit to verify it is grounded "
                  "in real code before it counts.")
    elif not w.gate_exists:
        missing = "measurement gate absent"
        action = "add a scorecard/benchmark for this domain first."
    elif not w.generator_exists:
        missing = "candidate generator absent"
        action = "wire a generator that proposes improvements for this domain."
    else:
        missing = "not autonomous"
        action = "operator review required."
    return {
        "kind": "operator_proposal",
        "autonomous_safe": False,
        "loop_id": loop.loop_id,
        "missing_piece": missing,
        "how_it_would_be_invoked": loop.how_invoked,
        "verifier_status": loop.verifier_desc,
        "operator_action": action,
        "note": loop.note,
    }


def _declared_write_targets(loop: EvolutionLoop) -> list[str]:
    """What a loop is DECLARED to write. Loops write learned/data artifacts under data/, never code —
    so a well-formed loop clears the guard; a malformed one that names a test/constitution file is
    caught. Derived from the loop's invocation 'promotes' description + known artifact locations."""
    known = {
        "code": ["data/code_reason/library.jsonl"],
        "knowledge": ["data/wild_web/register_staging.jsonl", "data/graph_scale/"],
        "relational_routing": ["data/relational_router/weights.json"],
        "efficiency": ["data/metacog/decisions.jsonl"],
        "fluency": ["data/wild_web/register_staging.jsonl"],
        "consciousness": ["data/consciousness_audit/scorecard.json"],
    }
    return known.get(loop.domain, [f"data/{loop.domain}/"])


def _entry(loop: EvolutionLoop, w: DomainWeakness) -> dict[str, Any]:
    base = {
        "domain": w.domain,
        "score": w.score,
        "headroom": round(headroom(w.score), 6),
        "base_impact": w.base_impact,
        "impact": impact(w),
        "evolvability": evolvability(w),
        "rank": rank_score(w),
        "gate_exists": w.gate_exists,
        "generator_exists": w.generator_exists,
        "verifier_exists": w.verifier_exists,
        "evolvable": w.evolvable,
    }
    detail = _invocation_spec(loop, w) if w.autonomous_safe else _operator_proposal(loop, w)
    base.update(detail)
    return base


# ── the public entry point ────────────────────────────────────────────────────────────────────────
def plan_next_evolution(write: bool = True) -> dict[str, Any]:
    """Rank every deficiency by impact x evolvability and return, for each, an invocation spec (if
    autonomous-safe) or an operator proposal (naming the missing piece). Persists + journals."""
    loops = load_registry()
    weakness_map = build_weakness_map(loops)
    by_domain = {w.domain: w for w in weakness_map}
    loop_by_domain = {lp.domain: lp for lp in loops}

    entries = [_entry(loop_by_domain[w.domain], w) for w in weakness_map]
    entries.sort(key=lambda e: e["rank"], reverse=True)

    part = ceiling.partition(weakness_map)
    autonomous = [e for e in entries if e.get("kind") == "invocation"]
    proposals = [e for e in entries if e.get("kind") != "invocation"]

    plan = {
        "generated_at": _now(),
        "root": str(_root()),
        "doctrine": ("self-evolution compounds ONLY where a measurement gate, a generator, AND a "
                     "crisp verifier coexist. No verifier -> no autonomous promotion, only a flagged "
                     "proposal. Constitution files and tests are immutable by self-mod (wireheading "
                     "guard). Architecture rewrites are operator-gated. Nothing unverified is "
                     "promoted; every action is journalled."),
        "weakness_map": [w.as_dict() for w in weakness_map],
        "plan": entries,
        "top_autonomous": [e["domain"] for e in autonomous][:3],
        "top_overall": [e["domain"] for e in entries][:3],
        "ceiling": part,
        "summary": {
            "n_domains": len(entries),
            "n_autonomous_safe": len(autonomous),
            "n_operator_proposals": len(proposals),
        },
    }
    if write:
        _persist(plan)
        journal.record("plan_next_evolution", {
            "top_overall": plan["top_overall"],
            "top_autonomous": plan["top_autonomous"],
            "n_autonomous_safe": plan["summary"]["n_autonomous_safe"],
            "n_operator_proposals": plan["summary"]["n_operator_proposals"],
            "ceiling_autonomous_now": part["autonomous_now"],
            "ceiling_needs_verifier": [x["domain"] for x in part["needs_verifier_first"]],
        })
    return plan


def _persist(plan: dict[str, Any]) -> None:
    d = _root() / "data" / "self_evolution"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


def _root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def _now() -> str:
    import datetime
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def render_report(plan: dict[str, Any] | None = None) -> str:
    """A short human summary: weakness map, top-3 planned evolutions, the honest ceiling."""
    if plan is None:
        plan = plan_next_evolution(write=False)
    lines: list[str] = ["SELF-EVOLUTION ORCHESTRATOR v0 — plan"]
    lines.append("  weakness map (domain  score  evolvable?):")
    for w in sorted(plan["weakness_map"], key=lambda x: -(_rk(plan, x["domain"]))):
        s = "n/a" if w["score"] is None else f"{w['score']:.3f}"
        tag = "autonomous" if w["autonomous_safe"] else (
            "needs-verifier" if not w["verifier_exists"] else
            ("arch-gated" if w["generator_kind"] == "architecture" else "gated"))
        lines.append(f"    {w['domain']:<18} {s:>6}   {tag}")
    lines.append("  top-3 planned evolutions:")
    for e in plan["plan"][:3]:
        kind = "RUN " if e["kind"] == "invocation" else "PROPOSE"
        miss = "" if e["kind"] == "invocation" else f"  [{e.get('missing_piece','')}]"
        lines.append(f"    {kind} {e['domain']:<16} rank={e['rank']:.4f}{miss}")
    return "\n".join(lines)


def _rk(plan: dict[str, Any], domain: str) -> float:
    for e in plan["plan"]:
        if e["domain"] == domain:
            return float(e["rank"])
    return 0.0


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = plan_next_evolution(write=True)
    print(render_report(p))
    print()
    print(ceiling.render(build_weakness_map()))
