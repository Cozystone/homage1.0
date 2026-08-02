# -*- coding: utf-8 -*-
"""Diet steering — RSI layer ①: the arena's WEAKNESS aims the web mining (owner 2026-07-12:
"→ ").

The speaker arena scores its voice on held-out seeds every burst. The seeds it scores LOWEST are
topics/registers the voice is thin on — exactly what the diet should feed next. This closes the
loop: evaluate → find the weakest topics → aim the web expedition at them → the voice fattens where
it was starving → re-evaluate. The diet feeds the surface CORPUS only (never a fact lane), so
targeting is safe: it changes WHAT the voice reads to practise on, not what is held true.

Bounded, decaying file (data/evolution/diet_targets.jsonl): each weak topic gets a strength that
fades over time, so a topic that stops being weak (because it got fed) stops being chased. The
browse_director prefers a live target when one outranks its default frontier pick — a soft steer,
never a hard override (the graph's own thin-topic frontier still leads when no target is pressing).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TARGETS_PATH = REPO / "data" / "evolution" / "diet_targets.jsonl"
_HALF_LIFE_S = 6 * 3600.0     # a target's pull halves every ~6h — fed topics fade out
_MAX_TARGETS = 40
_STOP = {"그", "이", "저", "것", "수", "때", "등", "및", "또", "즉"}


def _topic_of(seed: str) -> str:
    """The bare topic word a seed carries (/space stripped) — what to search the web for."""
    tok = re.split(r"\s+", str(seed or "").strip())[0] if seed else ""
    tok = re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|보다|처럼|같이)$", "", tok)
    return tok


def record_weakness(scored_seeds: list[tuple[str, float]], *, floor: float = 0.6) -> int:
    """Register the seeds a burst scored BELOW `floor` as diet targets (weak = needs feeding). Each
    is appended with a strength = how far below the floor it fell. Returns how many were recorded."""
    weak: list[dict[str, Any]] = []
    now = time.time()
    for seed, score in scored_seeds:
        topic = _topic_of(seed)
        if len(topic) < 2 or topic in _STOP or float(score) >= floor:
            continue
        weak.append({"topic": topic, "strength": round(min(1.0, floor - float(score)), 4), "ts": now})
    if not weak:
        return 0
    TARGETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TARGETS_PATH.open("a", encoding="utf-8") as f:
        for w in weak:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")
    # keep the file bounded (newest wins)
    rows = TARGETS_PATH.read_text(encoding="utf-8").splitlines()
    if len(rows) > _MAX_TARGETS * 3:
        TARGETS_PATH.write_text("\n".join(rows[-_MAX_TARGETS * 3:]) + "\n", encoding="utf-8")
    return len(weak)


def _live_targets() -> list[tuple[str, float]]:
    """Current weak topics with their TIME-DECAYED pull, strongest first. A topic seen multiple
    times accumulates; all pulls fade with the half-life so fed topics drop off on their own."""
    if not TARGETS_PATH.exists():
        return []
    now = time.time()
    agg: dict[str, float] = {}
    for ln in TARGETS_PATH.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(ln)
            age = max(0.0, now - float(d.get("ts") or now))
            decay = 0.5 ** (age / _HALF_LIFE_S)
            agg[str(d["topic"])] = agg.get(str(d["topic"]), 0.0) + float(d["strength"]) * decay
        except Exception:
            continue
    return sorted(((t, s) for t, s in agg.items() if s > 0.05), key=lambda kv: -kv[1])[:_MAX_TARGETS]


def next_target(recent: set[str], *, min_pull: float = 0.15) -> str | None:
    """The topic the diet most wants next, skipping anything just visited — or None if no target is
    pressing enough (let the graph's own thin-topic frontier lead). A soft steer, not an override."""
    for topic, pull in _live_targets():
        if pull >= min_pull and topic not in recent:
            return topic
    return None


def status() -> dict[str, Any]:
    tg = _live_targets()
    return {"targets": [{"topic": t, "pull": round(s, 3)} for t, s in tg[:10]], "count": len(tg)}
