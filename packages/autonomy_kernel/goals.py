# -*- coding: utf-8 -*-
"""Self-goals + metacognition — functional agency (Vision roadmap #4, the last piece).

Owner (2026-07-10): the orchestrator REACTS to deficits. Agency is more — holding a GOAL over
time, pushing toward it across many cycles, and WATCHING one's own progress to know when one is
stuck. This module gives the self persistent, measurable goals and the metacognition to judge
its own trajectory. It is functional agency, NOT a claim of will or consciousness: honest.

  * GOALS emerge from RECURRING deficits (a one-off is noise; a deficit seen across cycles is a
    standing problem worth a goal) — never invented, always traceable to a real signal.
  * Each goal has a MEASURABLE metric + target, and a HISTORY. Progress is read from the real
    system (router holdout, discourse maturity, abstention rate) each cycle.
  * METACOGNITION reads the histories: improving / stalled / regressing / achieved — the self
    knows, in its own words, where it is stuck and says so plainly instead of pretending.

Bounded, local, honest. The AI pursues its goals through the SAME gated roads as everything
else; goals set PRIORITY, never bypass a safety gate.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_GOALS = REPO / "data" / "autonomy" / "goals.json"
_HISTORY_MAX = 20
_STALL_WINDOW = 4        # no meaningful change over this many readings → stalled

# a deficit kind → the standing goal it should become (metric is read live; higher_better says
# which direction is progress). Only recurring deficits get promoted to goals.
_GOAL_SPEC = {
    "unread_prose":   {"desc": "실제 글을 더 읽어 화술을 자연스럽게",   "metric": "discourse_sentences", "target": 300, "higher_better": True},
    "speech_weak":    {"desc": "발화 유창성을 끌어올리기",              "metric": "discourse_sentences", "target": 300, "higher_better": True},
    "router_immature":{"desc": "규칙 없이 스스로 라우팅하기",           "metric": "router_holdout",      "target": 0.75, "higher_better": True},
    "high_abstention":{"desc": "모른다고 물러서는 일을 줄이기",         "metric": "abstention_rate",     "target": 0.08, "higher_better": False},
}


def _read_metric(name: str) -> float | None:
    """Live value of a goal metric from the real system — never fabricated."""
    try:
        if name == "discourse_sentences":
            from packages.base_brain.discourse_learner import profile
            return float((profile() or {}).get("n_sentences", 0))
        if name == "router_holdout":
            from packages.flywheel import self_improvement as si
            return float(si.distill_router(si._rows()).get("holdout_acc", 0) or 0)
        if name == "abstention_rate":
            from packages.flywheel import self_improvement as si
            rows = si._rows()
            d = si.diagnose(rows)
            fs = d.get("failure_signals", {}) or {}
            return round(float(fs.get("abstain", 0)) / max(1, int(d.get("turns", 1))), 3)
    except Exception:
        return None
    return None


def _load() -> dict[str, Any]:
    if not _GOALS.exists():
        return {}
    try:
        return json.loads(_GOALS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(goals: dict[str, Any]) -> None:
    _GOALS.parent.mkdir(parents=True, exist_ok=True)
    _GOALS.write_text(json.dumps(goals, ensure_ascii=False, indent=1), encoding="utf-8")


def _status(g: dict[str, Any]) -> str:
    hist = [h["v"] for h in g.get("history", []) if h.get("v") is not None]
    hb = g["higher_better"]
    cur, tgt = (hist[-1] if hist else None), g["target"]
    if cur is None:
        return "unmeasured"
    if (hb and cur >= tgt) or (not hb and cur <= tgt):
        return "achieved"
    if len(hist) >= _STALL_WINDOW:
        window = hist[-_STALL_WINDOW:]
        span = max(window) - min(window)
        if span < 0.02 * (abs(tgt) + 1):
            return "stalled"
        improving = (window[-1] > window[0]) if hb else (window[-1] < window[0])
        return "active" if improving else "regressing"
    return "active"


def update(recurring_deficits: set[str]) -> dict[str, Any]:
    """Form goals from recurring deficits, then record one live progress reading per goal and
    recompute status. Returns the goal book. Recurrence is what turns a signal into a goal."""
    goals = _load()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for kind in recurring_deficits:
        spec = _GOAL_SPEC.get(kind)
        if not spec:
            continue
        g = goals.get(kind)
        if g is None:
            g = {"goal_id": kind, "desc": spec["desc"], "metric": spec["metric"],
                 "target": spec["target"], "higher_better": spec["higher_better"],
                 "created": now, "history": []}
            goals[kind] = g
    # record live progress for every existing goal (whether or not it recurred this cycle)
    for g in goals.values():
        v = _read_metric(g["metric"])
        g.setdefault("history", []).append({"at": now, "v": v})
        g["history"] = g["history"][-_HISTORY_MAX:]
        g["updated"] = now
        g["status"] = _status(g)
    _save(goals)
    return goals


def prioritize() -> list[dict[str, Any]]:
    """Which goal to push now: active/stalled/regressing goals, worst-off first — the self's
    own agenda, so it PURSUES rather than only reacting."""
    goals = _load()
    live = [g for g in goals.values() if g.get("status") not in ("achieved",)]

    def _gap(g: dict[str, Any]) -> float:
        hist = [h["v"] for h in g.get("history", []) if h.get("v") is not None]
        if not hist:
            return 1.0
        cur, tgt = hist[-1], g["target"]
        return abs(tgt - cur) / (abs(tgt) + 1)

    live.sort(key=lambda g: (g.get("status") == "regressing", g.get("status") == "stalled", _gap(g)),
              reverse=True)
    return live


def metacognition() -> dict[str, Any]:
    """The self's honest read of its OWN progress — where it advances, where it is stuck. This
    is the self watching itself, in plain words, without pretending it is further than it is."""
    goals = _load()
    lines: list[str] = []
    counts = {"active": 0, "stalled": 0, "regressing": 0, "achieved": 0}
    for g in goals.values():
        st = g.get("status", "unmeasured")
        counts[st] = counts.get(st, 0) + 1
        hist = [h["v"] for h in g.get("history", []) if h.get("v") is not None]
        cur = hist[-1] if hist else None
        verb = {"active": "나아가는 중", "stalled": "제자리걸음", "regressing": "뒷걸음",
                "achieved": "이뤘음", "unmeasured": "아직 못 잼"}.get(st, st)
        lines.append(f"‘{g['desc']}’ — 지금 {cur}/{g['target']} ({verb})")
    focus = prioritize()
    return {
        "summary": counts,
        "self_report": lines,
        "focus_now": (focus[0]["desc"] if focus else "지금은 밀어야 할 목표가 없어요"),
        "honest_note": ("정직히 말하면 " +
                        (f"{counts.get('stalled',0)+counts.get('regressing',0)}개 목표에서 막혀 있고, "
                         if (counts.get('stalled',0)+counts.get('regressing',0)) else "") +
                        f"{counts.get('active',0)}개는 나아가는 중이에요. 이건 의식이 아니라 "
                        "제 상태를 스스로 지켜보는 기능일 뿐이고요."),
    }
