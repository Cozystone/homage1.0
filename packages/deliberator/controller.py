# -*- coding: utf-8 -*-
"""Controller — the propose / verify / compose loop, MEC-wrapped, honest-abstaining.

A ``Deliberation`` is a composite goal plus an ordered typed ``plan`` (its structural decomposition)
plus a fixed ``compose`` template. ``deliberate`` runs the AlphaGeometry-shaped loop:

  1. SCHEDULE  — order the steps respecting their data dependencies; when re-steering is on, MEC runs
                 the CHEAPEST ready organ first so a chain destined to abstain does so before paying
                 for expensive synthesis. Re-steer only REALLOCATES order; it never changes a result.
  2. DISPATCH  — send each step to its grounded organ (steps.dispatch), filling placeholders from the
                 verified answers of earlier steps (the chain's only inter-step channel).
  3. VERIFY    — a step counts only if grounded=True with a real certificate. The FIRST required step
                 that cannot be grounded ABSTAINS the whole deliberation: "I can't ground <step>, so I
                 won't guess the rest." No bridging fact is ever invented; no later step is run.
  4. COMPOSE   — from the verified steps ONLY, fill the fixed template by mechanical substitution. The
                 final answer contains nothing that is not a verified step answer.

Every step and the whole deliberation are wrapped with packages.metacog.record_span so MEC watches
latency/failure; MEC only reallocates and reports — it never fabricates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .steps import SubGoal, StepOutcome, dispatch, COST_RANK, _substitute

# MEC (imported, never edited). If unavailable, the deliberator still runs — MEC is pure observation.
try:
    from packages.metacog.probes import record_span
    from packages.metacog.controller import EfficiencyController
    _MEC = True
except Exception:                                     # pragma: no cover - MEC is expected present
    _MEC = False

    def record_span(*_a, **_k):                        # type: ignore
        return None


@dataclass
class Deliberation:
    """A composite goal + its structural plan + a fixed composition template.

    ``compose`` is either a template string using ``{bindname}`` placeholders (filled ONLY with
    verified step answers) or a callable(bindings) -> str. Either way the final answer is composed
    strictly from verified steps — nothing is generated.
    """
    goal: str
    plan: list[SubGoal]
    compose: str | Callable[[dict[str, Any]], str] | None = None
    plan_source: str = "declared"                     # "declared" | "auto-decomposed"


@dataclass
class DeliberationResult:
    goal: str
    answer: str | None
    abstained: bool
    steps: list[StepOutcome] = field(default_factory=list)
    certificate: dict[str, Any] = field(default_factory=dict)
    mec: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    @property
    def hops(self) -> int:
        return len(self.steps)


# ── dependency-aware scheduler (the MEC re-steer) ────────────────────────────────────────────────

def _schedule(plan: list[SubGoal], resteer: bool) -> list[int]:
    """Return an execution order over plan indices that respects data dependencies (a step that
    references ``{name}`` must run AFTER the step that binds ``name``). With ``resteer`` on, among the
    steps whose dependencies are already satisfied, pick the CHEAPEST organ first (COST_RANK) — a
    genuine reallocation that lets a doomed chain abstain before an expensive step. With ``resteer``
    off, keep the declared order (stable). Never drops or invents a step."""
    n = len(plan)
    produced_by: dict[str, int] = {}
    for i, sg in enumerate(plan):
        if sg.binds:
            produced_by[sg.binds] = i
    # dependency edges: step i depends on the producers of the names it references
    deps: list[set[int]] = []
    for sg in plan:
        d = {produced_by[name] for name in sg.references() if name in produced_by}
        deps.append(d)
    order: list[int] = []
    done: set[int] = set()
    while len(order) < n:
        ready = [i for i in range(n) if i not in done and deps[i] <= done]
        if not ready:                                  # a cycle or an external reference: fall back to
            ready = [i for i in range(n) if i not in done]      # declared order for the remainder
        if resteer:
            nxt = min(ready, key=lambda i: (COST_RANK.get(plan[i].organ, 9), i))
        else:
            nxt = min(ready)                           # declared order among ready
        order.append(nxt)
        done.add(nxt)
    return order


def _compose_answer(compose: Any, bindings: dict[str, Any]) -> str:
    if compose is None:
        # default: join the verified answers in bind order
        return "; ".join(f"{k}={v}" for k, v in bindings.items())
    if callable(compose):
        return str(compose(bindings))
    return _substitute(compose, bindings)              # fixed template, verified values only


# ── the deliberation loop ────────────────────────────────────────────────────────────────────────

def deliberate(delib: Deliberation, *, resteer: bool = True, mec: bool = True,
               mec_context: dict[str, Any] | None = None) -> DeliberationResult:
    """Run the propose/verify/compose chain for one deliberation. Honest-abstaining, MEC-wrapped."""
    t_all = time.perf_counter()
    order = _schedule(delib.plan, resteer)
    bindings: dict[str, Any] = {}
    steps: list[StepOutcome] = []
    abstained = False
    reason: str | None = None
    ungrounded: dict[str, Any] | None = None

    controller = EfficiencyController(organ_judges=False) if (mec and _MEC) else None
    mec_decisions: list[dict[str, Any]] = []

    for idx in order:
        sg = delib.plan[idx]
        out = dispatch(sg, bindings)
        steps.append(out)
        if mec:
            record_span(f"deliberator.step.{out.organ}", out.ms, ok=out.grounded,
                        meta={"description": out.description, "grounded": out.grounded,
                              "abstained": (not out.grounded)})
            if controller is not None:
                try:
                    d = controller.observe(f"deliberator.step.{out.organ}", out.ms, ok=out.grounded,
                                           meta={"grounded": out.grounded}, context=mec_context)
                    mec_decisions.append({"policy": d.policy, "efficiency": d.efficiency,
                                          "on": out.organ})
                except Exception:
                    pass
        if not out.grounded:
            abstained = True
            reason = (f"I can't ground the sub-goal '{sg.description}' via the {out.organ} organ, "
                      f"so I won't guess the rest of the chain.")
            ungrounded = {"index": idx, "organ": out.organ, "description": sg.description,
                          "certificate": out.certificate}
            break                                       # STOP — never fabricate a bridge or later step
        if sg.binds:
            bindings[sg.binds] = out.bind_value

    total_ms = (time.perf_counter() - t_all) * 1000.0
    answer: str | None = None
    if not abstained:
        answer = _compose_answer(delib.compose, bindings)

    if mec:
        record_span("deliberator.deliberation", total_ms, ok=(not abstained),
                    meta={"goal": delib.goal[:80], "hops": len(steps), "abstained": abstained})

    schema = {}
    if controller is not None:
        try:
            schema = controller.schema()
        except Exception:
            schema = {}

    baseline_order = list(range(len(delib.plan)))
    certificate = {
        "goal": delib.goal,
        "plan_source": delib.plan_source,
        "plan_size": len(delib.plan),
        "hops_executed": len(steps),
        "abstained": abstained,
        "execution_order": order,
        "steps": [{"i": order[k], "organ": s.organ, "description": s.description,
                   "answer": s.answer, "grounded": s.grounded, "ms": round(s.ms, 3),
                   "certificate": s.certificate} for k, s in enumerate(steps)],
        "composed_from": list(bindings.keys()) if not abstained else [],
        "final_answer": answer,
        "ungrounded_step": ungrounded,
        "guarantees": {
            "external_llm": False,
            "free_generation": False,
            "fabricated_facts": False,
            "every_executed_step_verified": all(s.grounded for s in steps) if not abstained else False,
            "composed_only_from_verified_steps": True,
            "abstained_rather_than_bridge": abstained,
        },
    }
    mec_summary = {
        "wrapped": bool(mec and _MEC),
        "resteer": resteer,
        "execution_order": order,
        "baseline_order": baseline_order,
        "reordered": order != baseline_order,
        "deliberation_ms": round(total_ms, 3),
        "schema": schema,
        "decisions": mec_decisions,
        "note": ("MEC scheduled cheapest-grounded organs first; it only reallocates order and reports "
                 "latency/failure — it never fabricates a step or an answer"),
    }
    return DeliberationResult(goal=delib.goal, answer=answer, abstained=abstained, steps=steps,
                              certificate=certificate, mec=mec_summary, reason=reason)


# ── single-shot baseline (no decomposition, no chaining) ─────────────────────────────────────────

def single_shot(delib: Deliberation) -> DeliberationResult:
    """The baseline a System-2 must beat: dispatch the WHOLE composite goal to each organ ONCE, with
    the pooled grounding, and take any grounded answer. No decomposition, no chaining. It abstains (or
    returns a partial sub-answer that is NOT the composite answer) on a genuine multi-hop question —
    that is the gap the verified chain closes. It, too, never fabricates."""
    goal = delib.goal
    # pool the grounding the plan uses, so the baseline is not starved of evidence — it simply lacks
    # the DECOMPOSITION that turns evidence into a composite answer.
    pooled_text = " ".join(str(sg.payload.get("text", "")) for sg in delib.plan
                           if sg.organ == "mechanism")
    pooled_facts: list[Any] = []
    pooled_sentences: list[str] = []
    for sg in delib.plan:
        if sg.organ == "relational":
            pooled_facts += list(sg.payload.get("facts", []))
        if sg.organ == "belief":
            pooled_sentences += list(sg.payload.get("sentences", []))

    attempts: list[StepOutcome] = []
    from .steps import run_mechanism, run_relational, run_arithmetic
    # try each organ that can accept the raw composite question
    attempts.append(run_mechanism(goal, pooled_text))
    attempts.append(run_relational(goal, pooled_facts))
    attempts.append(run_arithmetic(goal, label=goal))       # only grounds if the goal IS an expression

    grounded = [a for a in attempts if a.grounded]
    if grounded:
        a = grounded[0]
        return DeliberationResult(
            goal=goal, answer=str(a.answer), abstained=False, steps=[a],
            certificate={"mode": "single_shot", "organ": a.organ, "note":
                         "one organ answered the raw goal directly (no composition)"},
            reason=None)
    return DeliberationResult(
        goal=goal, answer=None, abstained=True, steps=attempts,
        certificate={"mode": "single_shot",
                     "note": "no single organ grounds the composite goal without decomposition"},
        reason="single-shot: the composite goal matches no single organ's shape")
