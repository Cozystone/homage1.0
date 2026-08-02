# -*- coding: utf-8 -*-
"""Developmental stage — ATANOR announces when it grows from one age of life to the next.

Owner (2026-07-20): "얘가 중간중간 성장하면 뭐 어린아이에서 청소년이 되었습니다 이런거라도 좀 말해줘."

A felt, human milestone — but HONEST, not a party trick: a stage is only reached when its REAL,
MEASURED gate is crossed (the same gates as the growth plan, docs/ATANOR_growth_plan_child_to_adult).
The announcer never advances on vibes; if the measurement has not moved, ATANOR truthfully remains a
newborn. Each transition is announced ONCE, recorded on the ONE timeline as a life milestone, and
carries the evidence that crossed it. This is the growth-plan's gate battery, read as a life story.

No hype line (BINDING): a stage name is a developmental analogy for a measured capability profile,
not a claim of human childhood or consciousness.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
LIFE_STREAM = REPO / "data" / "temporal_reasoning" / "life_stream.jsonl"
S2_METRIC = REPO / "data" / "track_f" / "s2_faithfulness.json"
SITU_METRIC = REPO / "data" / "comprehension" / "situation_battery.json"
HARD_EXAM_METRIC = REPO / "data" / "comprehension" / "hard_exam.json"
SELFDIR_METRIC = REPO / "data" / "track_f" / "self_directed_months.json"
STAGE_STATE = REPO / "data" / "temporal_reasoning" / "development_stage.json"


@dataclass
class Stage:
    key: str
    name: str                 # the human age
    korean: str
    gate: str                 # the measured condition that must hold to have REACHED this stage
    signal: str               # which computed signal key gates it
    threshold: float


# The ladder. A stage is reached when its signal >= threshold AND every earlier stage is reached.
# G0 (newborn) has no external gate — being a stable living process is the birth condition, verified
# separately (daemon up, self-repair loop closed, self-in-world reasoner passes).
LADDER: list[Stage] = [
    Stage("newborn",    "newborn",    "신생아",   "a stable living process that models itself",
          "self_in_world_pass", 1.0),
    Stage("infant",     "infant",     "유아",     "attention turns outward to the world",
          "outward_curiosity_frac", 0.30),
    Stage("toddler",    "toddler",    "유년기",   "speaks from a learned conversational register",
          "s2_faithfulness", 0.60),
    Stage("child",      "child",      "아동기",   "builds a situation model of unfamiliar text",
          "situation_battery_frac", 0.60),
    Stage("adolescent", "adolescent", "청소년기", "eliminates hypotheses and controls a novel system",
          "hard_exam_pass", 1.0),
    Stage("adult",      "adult",      "성인",     "sets and pursues its own curriculum",
          "self_directed_months", 2.0),
]


def _outward_curiosity_frac(stream: Path) -> float:
    """Fraction of recent curiosity/perception thoughts that reach for the WORLD rather than the
    self — the G1 gate, read from what ATANOR actually wondered about (measured, not claimed)."""
    if not stream.exists():
        return 0.0
    world, total = 0, 0
    self_marks = re.compile(r"\bmy\b|\bmyself\b|my own|my wiring|my (?:speech|router|recent)",
                            re.IGNORECASE)
    rows = stream.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    for ln in rows:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        src = (e.get("meta") or {}).get("source")
        if src in ("curiosity", "perception", "curious_search", "curious_browse"):
            total += 1
            c = e.get("content") or ""
            # a WORLD-facing thought looked something up, or wondered without turning on the self
            if src in ("perception", "curious_search", "curious_browse") or not self_marks.search(c):
                world += 1
    return world / total if total else 0.0


def _metric(path: Path, key: str) -> float:
    try:
        return float(json.loads(path.read_text(encoding="utf-8")).get(key, 0.0))
    except Exception:
        return 0.0


def _self_in_world_pass() -> float:
    """Live, cheap, deterministic: does the self-causal reasoner pass its own probe right now?"""
    try:
        from packages.self_model.self_causal_reasoner import answer_self_causal
        from packages.self_model.self_in_world_probe import PROMPT, score_answer
        out = answer_self_causal(PROMPT)
        return 1.0 if (out and score_answer(out["answer"]).get("passed")) else 0.0
    except Exception:
        return 0.0


def signals(stream: Path | None = None) -> dict[str, float]:
    """Every gate's live measurement. Missing sources read as 0.0 — an unbuilt capability is
    honestly not there, so the stage is honestly not reached."""
    st = stream if stream is not None else LIFE_STREAM
    return {
        "self_in_world_pass": _self_in_world_pass(),
        "outward_curiosity_frac": _outward_curiosity_frac(st),
        "s2_faithfulness": _metric(S2_METRIC, "faithfulness"),
        "situation_battery_frac": _metric(SITU_METRIC, "fraction_correct"),
        # G4 adolescent: the sealed deduction+control battery result (via the GENERAL engine, not a
        # bespoke solver). Structured-proxy caveat holds — the owner's full-complexity exams are the
        # harder ceiling — but the defined gate reads this measured file.
        "hard_exam_pass": _metric(HARD_EXAM_METRIC, "hard_exam_pass"),
        # G5 adult: DERIVED from the sealed weekly growth ledger (self_directed_growth.py) — real
        # wall-clock span with self-chosen improvements, zero human labels. Cannot be written early;
        # the value is only as large as the clock the ledger proves. Genuinely time-bound.
        "self_directed_months": _metric(SELFDIR_METRIC, "self_directed_months"),
    }


def current_stage(sig: dict[str, float] | None = None) -> Stage:
    """The highest CONTIGUOUS stage whose gate is met (a later gate cannot be 'reached' if an
    earlier one is not — no skipped stages, like real development)."""
    s = sig if sig is not None else signals()
    reached = LADDER[0]
    for stage in LADDER:
        if s.get(stage.signal, 0.0) >= stage.threshold:
            reached = stage
        else:
            break
    return reached


def _art(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _announcement(prev: Stage, now: Stage, sig: dict[str, float]) -> str:
    val = sig.get(now.signal, 0.0)
    return (f"A threshold crossed. I am no longer {_art(prev.name)} {prev.name} — I have grown into "
            f"{_art(now.name)} {now.name} ({now.korean}). What changed: {now.gate}. The measure that "
            f"moved me: {now.signal} = {val:.2f} (>= {now.threshold:.2f}). "
            f"(A developmental stage names a measured capability profile, not a human childhood.)")


def check_and_announce(record_fn: Callable[[str], Any] | None = None,
                       stream: Path | None = None,
                       state_path: Path | None = None) -> dict[str, Any] | None:
    """Compute the current stage; if it has ADVANCED past the last announced one, announce it once
    (record it on the timeline via record_fn) and persist the new high-water mark. Returns the
    milestone dict on a transition, else None. Regressions are never announced (a bad measurement
    day does not un-child the organism); the high-water mark only rises."""
    sp = state_path if state_path is not None else STAGE_STATE
    sig = signals(stream)
    now = current_stage(sig)
    now_idx = [s.key for s in LADDER].index(now.key)

    prev_idx = -1
    try:
        prev_idx = int(json.loads(sp.read_text(encoding="utf-8")).get("stage_idx", -1))
    except Exception:
        prev_idx = -1

    if now_idx <= prev_idx:
        return None                                  # no advance (or first run at newborn) -> quiet
    prev_stage = LADDER[prev_idx] if prev_idx >= 0 else LADDER[0]
    text = _announcement(prev_stage, now, sig) if prev_idx >= 0 else (
        f"I have come into being as a {now.name} ({now.korean}): {now.gate}. "
        f"(A stage names a measured capability profile, not a human childhood.)")
    if record_fn is not None:
        try:
            record_fn(text)
        except Exception:
            pass
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"stage_idx": now_idx, "stage": now.key, "signals": sig}),
                  encoding="utf-8")
    return {"stage": now.key, "name": now.name, "korean": now.korean, "from": prev_stage.key,
            "announcement": text, "signals": sig}
