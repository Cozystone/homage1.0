# -*- coding: utf-8 -*-
"""Policies — the RESTEER layer of MEC. A closed WHITELIST of bounded, auditable interventions.

When a judge fires (DETECT), exactly one re-steer may be taken. This module is the ONLY place an
action is allowed, and every action here is bounded by construction: switch among alternatives the
caller already offered, shrink a cap by a clamped factor, back off by a capped delay, escalate (never
silently), or abstain honestly. Nothing here spends unbounded compute, rewrites code, or fabricates a
target — the strongest safety property of a self-steering controller is that its action set is small,
closed, and each member is provably bounded.

Each policy declares: a PRECONDITION (when it applies), a bounded ACT (the directive it emits, with
its own clamps), and the EVIDENCE it carries into the decision journal. `resolve` tries the policies
in a fixed priority order and returns the first whose precondition holds — so an intervention outside
this whitelist is not merely discouraged, it is unreachable.

Honest boundary: a directive is a RECOMMENDATION the caller applies; MEC does not reach into another
module's control flow. The demo and the daemon honour directives explicitly. Control, not compulsion.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .probes import mec_on, _base_dir

# ---------------------------------------------------------------- control constants (declared)
# the re-steer ladder for a lane with NO alternative: retry (0..MAX_RETRIES-1) -> abstain honestly
# (MAX_RETRIES..ESCALATE_REPEAT-1) -> escalate to a human (>= ESCALATE_REPEAT). Kept as a strict
# ladder so each rung is reachable (retry must yield before abstain, abstain before escalation).
MAX_RETRIES = 3            # exhaust this many capped retries before abandoning the path
ESCALATE_REPEAT = 5        # a still-unresolved anomaly this persistent stops being self-handled -> operator
BACKOFF_BASE_MS = 50.0     # retry backoff schedule (bounded exponential)
BACKOFF_CAP_MS = 2000.0
REALLOCATE_MIN_SCALE = 0.25  # a cap may be shrunk to at most this fraction — never to zero (no starvation)
# background learners a controller may PAUSE under overload. Declared config (the same curated-structure
# category as a set-point list) — NOT discovered knowledge, and kept short and reversible.
DEFERRABLE_DAEMONS = ("roam_web", "overnight_advisor", "flywheel_miner", "world_expedition")

# the closed set of directive names MEC may ever emit. Anything else is a bug, not a policy.
WHITELIST = frozenset({
    "switch_strategy", "reallocate", "retry_with_backoff", "escalate_to_operator",
    "abort_and_abstain", "steady",
})


def decisions_path() -> Path:
    return _base_dir() / "decisions.jsonl"


@dataclass
class Finding:
    """One DETECT result: what looks inefficient, how bad, and the evidence behind it.
    `repeat` is how many times this same (kind, span) already fired recently — persistence."""
    kind: str                      # slow_span | failure_concentration | high_failure | overload | commitment_thrash
    span: str
    severity: float                # regularized sigmas over baseline (or a pressure/rate in context)
    evidence: dict[str, Any] = field(default_factory=dict)
    repeat: int = 0


@dataclass
class ActionResult:
    """A bounded re-steer decision, ready to journal and to hand back to the caller."""
    policy: str
    directive: dict[str, Any]
    evidence: dict[str, Any]
    bounded: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "directive": self.directive, "evidence": self.evidence,
                "bounded": self.bounded, "note": self.note}


def _steady(reason: str = "within baselines") -> ActionResult:
    return ActionResult(policy="steady", directive={"directive": "steady"}, evidence={"reason": reason},
                        bounded=True, note=reason)


def _alternatives(context: dict[str, Any] | None) -> tuple[str | None, list[str]]:
    ctx = context or {}
    current = ctx.get("current")
    alts = [a for a in (ctx.get("alternatives") or []) if a != current]
    return current, alts


# ---------------------------------------------------------------- the policies (priority order)

def _p_escalate(f: Finding, snap: dict[str, Any], ctx: dict[str, Any] | None) -> ActionResult | None:
    """Persistent or critical trouble the controller could not fix itself -> tell the operator.
    NEVER silent: this always emits a directive that a human is meant to see."""
    critical_overload = f.kind == "overload" and float(f.evidence.get("rss_pressure", 0.0)) >= 0.95
    if f.repeat >= ESCALATE_REPEAT or critical_overload:
        return ActionResult(
            policy="escalate_to_operator",
            directive={"directive": "escalate_to_operator", "operator": True, "silent": False,
                       "span": f.span, "kind": f.kind},
            evidence={**f.evidence, "repeat": f.repeat, "critical_overload": critical_overload},
            note=f"unresolved {f.kind} on {f.span} (x{f.repeat}) — escalated to operator")
    return None


def _p_reallocate(f: Finding, snap: dict[str, Any], ctx: dict[str, Any] | None) -> ActionResult | None:
    """Overload or workspace thrash -> reclaim compute: shrink search caps and defer background daemons.
    The shrink factor is CLAMPED to [REALLOCATE_MIN_SCALE, 1.0] (never starves the work to zero)."""
    if f.kind not in ("overload", "commitment_thrash"):
        return None
    pressure = float(f.evidence.get("rss_pressure") or snap.get("rss_pressure") or 0.0)
    # prefer the organism's own metabolic load-shedding signal if the hormone field is available
    scale = None
    try:
        from packages.neural_emotion.metabolic_governor import regime
        levels = (ctx or {}).get("hormones")
        if isinstance(levels, dict):
            scale = 1.0 - float(regime(levels).get("load_shedding", 0.0))
    except Exception:
        scale = None
    if scale is None:
        scale = 1.0 - pressure                              # fall back to raw memory pressure
    scale = max(REALLOCATE_MIN_SCALE, min(1.0, round(scale, 3)))
    return ActionResult(
        policy="reallocate",
        directive={"directive": "reallocate", "search_cap_scale": scale,
                   "defer_daemons": list(DEFERRABLE_DAEMONS)},
        evidence={**f.evidence, "rss_pressure": round(pressure, 4)},
        note=f"overload/thrash -> search caps x{scale}, defer {len(DEFERRABLE_DAEMONS)} background daemons")


def _p_switch(f: Finding, snap: dict[str, Any], ctx: dict[str, Any] | None) -> ActionResult | None:
    """The headline re-steer: an operation is anomalously slow/failing AND the caller offered another
    lane -> switch to it. Bounded: the target is chosen ONLY from the caller's own alternatives."""
    if f.kind not in ("slow_span", "failure_concentration", "high_failure"):
        return None
    current, alts = _alternatives(ctx)
    if not alts:
        return None
    target = alts[0]
    return ActionResult(
        policy="switch_strategy",
        directive={"directive": "switch_strategy", "span": f.span, "from": current, "to": target},
        evidence={**f.evidence, "alternatives": (ctx or {}).get("alternatives")},
        note=f"{f.span} {f.kind} (severity {f.severity}) -> switch {current}->{target}")


def _p_retry(f: Finding, snap: dict[str, Any], ctx: dict[str, Any] | None) -> ActionResult | None:
    """A transient slow/failed span with no alternative lane -> retry with a CAPPED exponential backoff."""
    if f.kind not in ("slow_span", "high_failure") or f.repeat >= MAX_RETRIES:
        return None                                         # retries exhausted -> yield to abort/escalate
    attempt = int(f.repeat) + 1
    backoff = min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * (2 ** (attempt - 1)))
    return ActionResult(
        policy="retry_with_backoff",
        directive={"directive": "retry_with_backoff", "attempt": attempt,
                   "backoff_ms": round(backoff, 1), "max_retries": MAX_RETRIES},
        evidence={**f.evidence, "attempt": attempt},
        note=f"{f.span} transient trouble -> retry #{attempt} after {backoff:.0f}ms")


def _p_abort(f: Finding, snap: dict[str, Any], ctx: dict[str, Any] | None) -> ActionResult | None:
    """No alternative, retries exhausted -> abort and abstain HONESTLY rather than burn compute on a
    path that is not working. Abstention is the truthful outcome, not a failure to hide."""
    if f.kind in ("slow_span", "high_failure") and f.repeat >= MAX_RETRIES and not _alternatives(ctx)[1]:
        return ActionResult(
            policy="abort_and_abstain",
            directive={"directive": "abort_and_abstain", "honest": True, "span": f.span},
            evidence={**f.evidence, "repeat": f.repeat},
            note=f"{f.span} unrecoverable after {f.repeat} tries and no alternative -> honest abstain")
    return None


# fixed priority order — resolve returns the FIRST match, so the reachable action set is exactly this list
_PRIORITY = (_p_escalate, _p_reallocate, _p_switch, _p_retry, _p_abort)


def resolve(finding: Finding | None, snap: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None) -> ActionResult:
    """Map a DETECT finding to a bounded re-steer from the whitelist. No finding, or the kill-switch
    off, -> steady (a no-op). Guarantees the returned policy is in WHITELIST."""
    if not mec_on():
        return _steady("mec_off")
    if finding is None:
        return _steady("no finding")
    snap = snap or {}
    for policy in _PRIORITY:
        res = policy(finding, snap, context)
        if res is not None:
            assert res.policy in WHITELIST, f"policy '{res.policy}' escaped the whitelist"
            return res
    return _steady(f"no policy precondition met for {finding.kind}")


def journal_decision(result: ActionResult, finding: Finding | None, snap: dict[str, Any]) -> None:
    """Append the re-steer to the auditable decision ledger with its full evidence. Never raises.
    Steady no-ops are NOT journalled (the ledger records interventions, keeping it a signal not noise)."""
    if not mec_on() or result.policy == "steady":
        return
    try:
        rec = {
            "ts": round(time.time(), 3),
            "policy": result.policy,
            "directive": result.directive,
            "kind": None if finding is None else finding.kind,
            "span": None if finding is None else finding.span,
            "severity": None if finding is None else round(finding.severity, 4),
            "repeat": None if finding is None else finding.repeat,
            "evidence": result.evidence,
            "snapshot": snap,
            "bounded": result.bounded,
            "note": result.note,
        }
        p = decisions_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recent_decisions(window: int = 100) -> list[dict[str, Any]]:
    """The tail of the decision ledger — for the controller's repeat-counting and for /ops audit."""
    p = decisions_path()
    if not p.exists():
        return []
    try:
        rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return rows[-window:]
    except Exception:
        return []
