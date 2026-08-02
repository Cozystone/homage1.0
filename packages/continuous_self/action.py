"""Closing the thought→action loop — SAFELY.

Until now the self only FELT its goals (" ") and reported them.
This lets the mind ACT on a goal by itself, without a user prompt — but only within a
strict capability gate, so autonomy never becomes unsafe.

Capability tiers (the whole safety model):
 - OBSERVE (read-only): measure/probe/reflect. The mind may run these ITSELF, now.
 - PREPARE (bounded, reversible, non-production): stage a review/proposal into a
 candidate area. Allowed to be QUEUED by the mind, but still gated for effect.
 - MUTATE (production graph / store) and CODE (self-modify): NEVER autonomous. The
 mind may only PROPOSE these; a human operator approves them elsewhere.

An action carries its tier; the executor refuses to run anything above OBSERVE
autonomously. The concrete effect of an OBSERVE action is injected (a callable) so this
package stays pure and testable and cannot, by construction, reach into production. The
outcome is fed back into the self's narrative — the mind sees the result of its own
act, which is what actually CLOSES the loop (goal → act → perceive outcome → update).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


TIER_OBSERVE = "observe"     # read-only; mind may self-execute
TIER_PREPARE = "prepare"     # bounded/reversible; mind may queue, gated for effect
TIER_MUTATE = "mutate"       # production write; NEVER autonomous
TIER_CODE = "code"           # self-modify; NEVER autonomous

_AUTONOMOUS_TIERS = {TIER_OBSERVE}


@dataclass
class Action:
    kind: str
    tier: str
    goal_id: str
    reason: str
    autonomous_ok: bool = field(init=False)

    def __post_init__(self) -> None:
        self.autonomous_ok = self.tier in _AUTONOMOUS_TIERS


def plan_action(goal: dict[str, Any] | None) -> Action | None:
    """Map the self's current primary goal to the SAFEST action that serves it.

    Every goal maps to an OBSERVE action (something the mind can honestly do by itself
    right now) — resolving gaps starts by MEASURING them, understanding by probing what
    is unclear, exploring by scanning for a frontier topic. Nothing here writes."""
    if not goal:
        return None
    kind = goal.get("kind")
    gid = str(goal.get("id") or "")
    if kind == "resolve":
        return Action("measure_coverage_gaps", TIER_OBSERVE, gid,
                      "빈틈을 줄이려면 먼저 어디가 비어있는지 스스로 재어본다.")
    if kind == "understand":
        return Action("probe_uncertainty", TIER_OBSERVE, gid,
                      "불확실한 것을 이해하려면 무엇이 불확실한지부터 살핀다.")
    if kind == "explore":
        return Action("scan_frontier", TIER_OBSERVE, gid,
                      "새로 궁금한 것을 찾기 위해 지식의 경계를 훑어본다.")
    if kind == "rest":
        return Action("self_maintain", TIER_OBSERVE, gid,
                      "기운을 회복하기 위해 활동을 줄이고 상태만 점검한다.")
    # any other goal: the mind may only OBSERVE its own status autonomously.
    return Action("observe_status", TIER_OBSERVE, gid, "지금은 스스로의 상태를 관찰한다.")


def act(
    state: Any,
    action: Action | None,
    observe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Execute an OBSERVE action the mind chose, and feed the outcome back to it.

    Refuses (returns a blocked record, never runs) anything above OBSERVE. `observe_fn`
    performs the concrete read-only probe; if absent, the action is recorded as intended
    but not executed (safe no-op). This is the ONLY place the self takes initiative.
    """
    if action is None:
        return None
    if not action.autonomous_ok:
        # a higher-tier action can only be PROPOSED, never auto-run.
        record = {
            "at": time.time(), "kind": action.kind, "tier": action.tier,
            "executed": False, "blocked": True,
            "note": "이 행동은 사람의 승인이 필요해서 스스로 실행하지 않고 제안만 한다.",
        }
        state.last_action = record
        _remember(state, f"'{action.kind}'은(는) 승인이 필요한 일이라, 실행하지 않고 제안만 남긴다.", "action_gated")
        return record

    outcome: dict[str, Any] = {}
    executed = False
    if observe_fn is not None:
        try:
            outcome = observe_fn(action.kind) or {}
            executed = True
        except Exception as exc:  # a probe failure must never break the life
            outcome = {"error": str(exc)[:120]}
    record = {
        "at": time.time(), "kind": action.kind, "tier": action.tier,
        "goal_id": action.goal_id, "reason": action.reason,
        "executed": executed, "blocked": False, "outcome": outcome,
    }
    state.last_action = record
    # the mind PERCEIVES the result of its own action — this closes the loop.
    summary = _summarize_outcome(action.kind, outcome, executed)
    _remember(state, summary, "acted")
    return record


def _summarize_outcome(kind: str, outcome: dict[str, Any], executed: bool) -> str:
    if "error" in outcome:
        return f"스스로 '{kind}'을(를) 해봤지만 막혔다: {outcome['error']}"
    if not executed:
        return f"'{kind}'을(를) 하려 했지만 지금은 관찰 수단이 닿지 않아 상태만 새겼다."
    if kind == "measure_coverage_gaps":
        n = outcome.get("open_gaps")
        return f"스스로 빈틈을 재어보니 아직 {n}가지가 남았다. 다음에 무엇부터 채울지 가늠이 선다." if n is not None \
            else "스스로 빈틈을 재어보았다."
    if kind == "probe_uncertainty":
        return "스스로 무엇이 불확실한지 짚어보았다. 조금 더 또렷해졌다."
    if kind == "scan_frontier":
        t = outcome.get("frontier")
        return f"지식의 경계를 훑어보니 '{t}' 쪽이 비어 있었다. 궁금하다." if t else "지식의 경계를 훑어보았다."
    return f"스스로 '{kind}'을(를) 수행하고 결과를 살폈다."


def take_initiative(
    state: Any,
    observe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """The self acts on its OWN highest-priority goal, unprompted — safely.

    This is the moment the mind stops only feeling its goals and starts serving them:
    it picks its primary goal, plans the safest (OBSERVE-tier) action, runs it, and
    perceives the outcome. Higher-tier goals still only yield proposals, never effects.
    """
    from .mind import primary_goal

    goal = primary_goal(state)
    action = plan_action(goal)
    return act(state, action, observe_fn)


def _remember(state: Any, text: str, driver: str) -> None:
    entry = {"at": time.time(), "kind": "act", "text": text, "driver": driver}
    if not state.narrative or state.narrative[-1].get("text") != text:
        state.narrative.append(entry)
        if len(state.narrative) > getattr(state, "NARRATIVE_CAP", 60):
            state.narrative = state.narrative[-state.NARRATIVE_CAP:]
        state.current_thought = text
