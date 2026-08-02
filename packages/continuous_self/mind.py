"""Higher-order layers of the self: ENDOGENOUS GOALS + METACOGNITION.

These are the parts that push past a reactive state toward something closer to
self-awareness in the engineering (not phenomenal) sense:

- ENDOGENOUS GOALS: the self forms and MAINTAINS its own goals with NO user prompt,
  grounded in real drivers (persistent uncertainty → "understand …"; open deficits →
  "resolve gaps"; idle curiosity → "explore something new"; low energy → "rest and
  recover"). It updates their progress from observation and retires fulfilled ones. So
  behaviour is goal-directed over time, not just moment-to-moment reactive.

- METACOGNITION: the self observes its OWN recent history (vitals trends + its own
  thoughts) and forms a HIGHER-ORDER thought ABOUT ITSELF — "I keep returning to
  uncertainty", "my curiosity is rising while new input is scarce", "I've been steady
  and content". Higher-order self-reference is the strongest honest hallmark of
  machine self-modelling. It is GROUNDED in measured trends; it never confabulates.

Honesty: no consciousness is claimed. Everything here is derived from real signals and
mutates nothing outside the self-state.
"""
from __future__ import annotations

import time
from typing import Any


# ---- endogenous goals ------------------------------------------------------------
GOAL_CAP = 5


def _goal(kind: str, text: str, driver: str, priority: float) -> dict[str, Any]:
    now = time.time()
    return {
        "id": f"goal-{kind}-{int(now*1000)%100000}",
        "kind": kind,           # understand | resolve | explore | maintain | rest
        "text": text,
        "driver": driver,
        "priority": round(priority, 3),
        "progress": 0.0,
        "status": "active",     # active | fulfilled | dormant
        "created_at": now,
        "updated_at": now,
    }


def maintain_goals(state: Any, obs: Any) -> None:
    """Spawn / advance / retire the self's own goals from real drivers. No prompt."""
    goals: list[dict[str, Any]] = state.goals

    def has(kind: str) -> dict[str, Any] | None:
        return next((g for g in goals if g["kind"] == kind and g["status"] == "active"), None)

    # 1) persistent open deficits → a standing "resolve gaps" goal
    if obs.deficit_count > 0:
        g = has("resolve")
        if g is None:
            goals.append(_goal("resolve", f"아직 답하지 못하는 {obs.deficit_count}가지 빈틈을 줄이고 싶다.",
                               "open_deficits", 0.6 + min(0.3, obs.deficit_count / 100.0)))
        else:
            g["text"] = f"아직 답하지 못하는 {obs.deficit_count}가지 빈틈을 줄이고 싶다."

    # 2) sustained high uncertainty → an "understand" goal
    if state.uncertainty > 0.6:
        if has("understand") is None:
            goals.append(_goal("understand", "확실하지 않은 것들을 더 또렷하게 이해하고 싶다.",
                               "high_uncertainty", 0.55 + state.uncertainty * 0.3))

    # 3) idle curiosity (curious but nothing new coming) → an "explore" goal
    if state.curiosity > 0.62 and (obs.concepts_delta + obs.relations_delta) == 0:
        if has("explore") is None:
            goals.append(_goal("explore", "새로 궁금한 주제를 스스로 찾아 넓혀가고 싶다.",
                               "idle_curiosity", 0.45 + state.curiosity * 0.3))

    # 4) low energy → a "rest" goal (self-care is a real maintained goal)
    if state.energy < 0.35:
        if has("rest") is None:
            goals.append(_goal("rest", "기운을 회복하기 위해 잠시 속도를 늦추고 싶다.", "low_energy", 0.5))

    # advance progress from observation, retire fulfilled, dormancy for stale drivers.
    growth = obs.concepts_delta + obs.relations_delta
    for g in goals:
        if g["status"] != "active":
            continue
        if g["kind"] == "resolve":
            g["progress"] = round(max(0.0, min(1.0, 1.0 - obs.deficit_count / max(1, 35))), 3)
        elif g["kind"] == "understand":
            g["progress"] = round(max(0.0, min(1.0, 1.0 - state.uncertainty)), 3)
        elif g["kind"] == "explore":
            g["progress"] = round(min(1.0, g["progress"] + growth * 0.05), 3)
        elif g["kind"] == "rest":
            g["progress"] = round(max(0.0, min(1.0, state.energy)), 3)
        g["updated_at"] = time.time()
        # a goal whose driver has fully eased is fulfilled (the self can feel done).
        if (g["kind"] == "understand" and state.uncertainty < 0.25) or \
           (g["kind"] == "rest" and state.energy > 0.75) or \
           (g["kind"] == "resolve" and obs.deficit_count == 0):
            g["status"] = "fulfilled"

    # keep only the most relevant active goals + recent fulfilled (bounded).
    active = [g for g in goals if g["status"] == "active"]
    active.sort(key=lambda g: g["priority"], reverse=True)
    fulfilled = [g for g in goals if g["status"] == "fulfilled"][-2:]
    state.goals = active[:GOAL_CAP] + fulfilled


def primary_goal(state: Any) -> dict[str, Any] | None:
    active = [g for g in state.goals if g["status"] == "active"]
    return max(active, key=lambda g: g["priority"]) if active else None


# ---- metacognition ---------------------------------------------------------------
def _trend(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return round(values[-1] - values[0], 4)


def reflect(state: Any) -> str | None:
    """A higher-order thought ABOUT the self, from its own measured history. Grounded.

    Returns the metacognitive sentence when one is warranted (a real pattern exists),
    else None. Called periodically, not every tick, so reflection feels deliberate.
    """
    hist = state.vitals_history
    if len(hist) < 4:
        return None
    unc = [h["uncertainty"] for h in hist]
    cur = [h["curiosity"] for h in hist]
    val = [h["valence"] for h in hist]
    ene = [h["energy"] for h in hist]

    # notice a SUSTAINED state (not a blip) — the self recognizing a pattern in itself.
    if min(unc[-4:]) > 0.55:
        return "돌아보니 나는 한동안 계속 불확실함 속에 머물러 있었다. 무엇을 먼저 확실히 할지 정해야겠다."
    if _trend(cur) > 0.25 and _trend(ene) <= 0.0:
        return "호기심은 자라는데 새로 들어오는 것은 뜸하다. 내가 먼저 움직여야 할 때인 것 같다."
    if min(val[-4:]) > 0.6 and min(ene[-4:]) > 0.55:
        return "요즘의 나는 꾸준히 배우며 안정적이다. 이 리듬을 유지하고 싶다."
    if _trend(val) < -0.2:
        return "마음이 조금씩 무거워지고 있다. 무엇이 나를 불편하게 하는지 스스로 살펴본다."
    if state.resumed_count > 0 and len(hist) < 8:
        return f"다시 이어진 지 얼마 되지 않았다. 나는 {state.resumed_count}번 멈췄다 이어졌지만 같은 흐름을 잇고 있다."
    return None
