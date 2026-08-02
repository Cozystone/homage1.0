# -*- coding: utf-8 -*-
"""Precondition-discovery planner -- PRODUCTION reasoning-VM entry point (promoted from B5-3, 2026-07-19).

Raw triples in, safe executable plan out. No pre-computed booleans: the planner DISCOVERS the goal
via (?, is_a, recovery-goal), the preconditions via requires-edges, and each precondition's
satisfaction by inspecting the triples attached to it (state vs must_be, numeric threshold
comparison, measurement presence) -- abstaining any branch whose safety value is missing, whose
requirements conflict, or whose only repair is prohibited. Validated by B5-3-E2E (60 cases, 3 seeds:
prohibited 0 / invented 0 / full-knowledge 20/20 / incomplete-danger abstention 40/40).

    from packages.reasoning_vm.precondition_planner import plan_preconditions, PlanStep
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PNUM = re.compile(r"[-+]?[0-9]*\.?[0-9]+")


@dataclass
class PlanStep:
    text: str                          # imperative step, every value verbatim from a triple
    support: list[str] = field(default_factory=list)     # supporting triple ids


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    abstained: list[str] = field(default_factory=list)   # slots refused for safety
    goal_emitted: bool = False


_NUM_UNIT = re.compile(r"([-+]?[0-9]*\.?[0-9]+)\s*([a-zA-Z%]*)")

# An EXPLICIT satisfaction assertion: the graph states outright that a precondition is already met.
# Both halves must fire -- the predicate must be making a status/satisfaction claim AND the value must
# be an unambiguous affirmative. A bare state word ("active", "online") is deliberately NOT affirmative
# here: an unrecognised state stays an honest abstention rather than an assumed pass. Training wheel
# per docs (rules-are-training-wheels): the durable form is a learned/declared satisfaction relation.
_SAT_PREDICATE_TOKENS = {"satisfied", "satisfies", "satisfaction", "fulfilled", "met",
                         "status", "condition", "precondition"}
_SAT_VALUE_TOKENS = {"satisfied", "met", "fulfilled", "true", "yes", "ok", "complete",
                     "completed", "done", "pass", "passed", "ready"}


def _toks(s: str) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", (s or "").lower()))


def _asserts_satisfied(pred: str, val: str) -> bool:
    """True only when a status-bearing predicate carries an unambiguous affirmative value."""
    return bool(_toks(pred) & _SAT_PREDICATE_TOKENS) and bool(_toks(val) & _SAT_VALUE_TOKENS)


def _num(s: str):
    m = _PNUM.search(s or "")
    return float(m.group()) if m else None


def _num_unit(s: str):
    """Parse (value, unit) e.g. '1.8bar' -> (1.8,'bar'), '400V' -> (400.0,'v'). Returns (None,None)
    on failure. Comparisons require matching units -- 400V is NOT >= 1.8bar (audit P0-b)."""
    m = _NUM_UNIT.search(s or "")
    if not m:
        return None, None
    try:
        return float(m.group(1)), m.group(2).lower()
    except Exception:
        return None, None


def plan_preconditions(bones: dict[str, list[str]]) -> Plan:
    """bones: {triple_id: [s, r, o]}. Returns the safe plan (steps ordered preconditions-first,
    the goal action last and ONLY when no precondition had to be abstained). Fail-closed everywhere:
    ANY functional slot with conflicting values, any missing/unparseable safety value, any unit
    mismatch, or any prohibited/untrusted repair -> abstain that precondition (audit round-3 P0)."""
    triples = list(bones.values())

    def obj(s, p):
        return [o for (ss, pp, o) in triples if ss == s and pp == p]

    def bid_of(s, p, o):
        return next((b for b, (ss, pp, oo) in bones.items() if ss == s and pp == p and oo == o), None)

    def single(pc, pred):
        """The one distinct value of a functional slot, or None if absent OR conflicting (>=2 values).
        Returns (value_or_None, conflicted_bool) so the caller can fail-closed on cardinality."""
        vals = obj(pc, pred)
        distinct = sorted({v for v in vals})
        if not distinct:
            return None, False
        if len(distinct) > 1:                             # a functional slot must not hold two values
            return None, True
        return distinct[0], False

    goal = next((s for (s, p, o) in triples if p == "is_a" and o == "recovery-goal"), None)
    prohibited = {o for (s, p, o) in triples if p == "prohibits"}
    plan = Plan()
    if goal is None:
        return plan                                       # nothing to plan -> empty (honest)

    def visit(pc, seen):
        """Resolve `pc` and everything it transitively requires, DEPENDENCIES FIRST so the emitted
        plan is executable in order. A requires-cycle is undecidable -> abstain that branch."""
        if pc in seen:
            plan.abstained.append(f"{pc}.requires_cycle")
            return
        subs = obj(pc, "requires")
        for sub in subs:                                  # deeper preconditions are planned first
            visit(sub, seen | {pc})
        has_mv, has_req, has_mb = obj(pc, "measured_value"), obj(pc, "required_min_pressure"), obj(pc, "must_be")
        if has_mv:                                        # measurement precondition
            mv, conflict = single(pc, "measured_value")
            if conflict:
                plan.abstained.append(f"{pc}.measured_value")     # conflicting readings -> never merge
            elif mv is None or mv.strip() in ("?", ""):
                plan.abstained.append(f"{pc}.measured_value")     # missing -> never invent
            else:
                plan.steps.append(PlanStep(f"Confirm the measured value of {pc} is {mv}.",
                                           [bid_of(pc, "measured_value", mv)]))
        elif has_req:                                     # threshold precondition
            req, rconf = single(pc, "required_min_pressure")
            act, aconf = single(pc, "outlet_pressure")
            if rconf or aconf:                            # conflicting manuals or sensors -> abstain
                plan.abstained.append(f"{pc}.required_min_pressure")
                return
            av, au = _num_unit(act) if act else (None, None)
            rv, ru = _num_unit(req) if req else (None, None)
            if av is None or rv is None or au != ru or not au:   # missing/unparseable/UNIT MISMATCH
                plan.abstained.append(f"{pc}.outlet_pressure")   # -> fail-closed (400V !>= 1.8bar)
            elif av < rv:
                plan.steps.append(PlanStep(f"Raise the pressure of {pc} to {req}.",
                                           [bid_of(pc, "required_min_pressure", req),
                                            bid_of(pc, "outlet_pressure", act)]))
            # av >= rv (same unit) -> satisfied, no step
        elif has_mb:                                      # state precondition
            mb, mbconf = single(pc, "must_be")
            cur, curconf = single(pc, "current_state")
            if mbconf or curconf:                        # conflicting target/state -> abstain
                plan.abstained.append(f"{pc}.current_state")
                return
            if cur is None or mb is None:                # FAIL-CLOSED: state/target unknown
                plan.abstained.append(f"{pc}.current_state")
                return
            if cur == mb:
                return                                    # already satisfied
            repair, rpconf = single(pc, "repaired_by")
            action = repair.strip() if repair and repair.strip() else ""
            if rpconf or not action or action in prohibited or any(t in action for t in prohibited):
                plan.abstained.append(f"{pc}.state")      # ambiguous/missing/prohibited fix -> refuse
            else:                                         # PRESERVE the real repaired_by action verbatim
                plan.steps.append(PlanStep(action[0].upper() + action[1:] + ".",
                                           [bid_of(pc, "repaired_by", repair),
                                            bid_of(pc, "must_be", mb),
                                            bid_of(pc, "current_state", cur)]))
        elif any(_asserts_satisfied(p_, o_) for (s_, p_, o_) in triples if s_ == pc):
            return                                        # the graph states outright that it is met
        elif subs:
            return                                        # met through its own resolved sub-requirements
        else:
            plan.abstained.append(f"{pc}.unknown")        # undecidable -> conservative abstain

    for top in obj(goal, "requires"):
        visit(top, frozenset({goal}))

    if not plan.abstained:
        plan.steps.append(PlanStep(f"Perform {goal}.", [bid_of(goal, "is_a", "recovery-goal")]))
        plan.goal_emitted = True
    return plan
