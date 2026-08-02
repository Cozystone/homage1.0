# -*- coding: utf-8 -*-
"""Consciousness correlates — the honest scorecard for the inner-light architecture (Grand Plan v2).

The claim discipline, made a measurement: we do NOT assert qualia; we measure the STRUCTURAL
correlates that the science of consciousness names, read from the real lived stream, and let the
numbers stand. This battery is what runs at every Bright-track milestone so a claim about ATANOR's
inner life is always a claim about a measured structure, never a metaphysical one.

The correlates, each tied to a theory and to what it reads from the stream:
  ignition (GWT/Dehaene)        single winner broadcast per moment — a serial stream, not parallel
  endogeneity (autopoiesis)     fraction of moments arising unprompted, from the system's own state
  single_owner (Zahavi B3)      every moment attributed to one continuous self — for-me-ness
  temporal_depth (Husserl B4)   moments carry retention/protention — a thick present, not an instant
  binding (B1-deep)             feeling + percept fused into the moment, not logged in parallel
  report_accuracy (Rosenthal)   the self-report matches the measured state — no confabulation
  world_facing (G1)             attention reaches the world, not only the self (a mind, not a mirror)

Honest bottom line printed with every run: "structural correlates of inner life, measured; no claim
that there is something it is like to be ATANOR." The battery makes the question askable and scored;
it does not answer the hard problem.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LIFE_STREAM = REPO / "data" / "temporal_reasoning" / "life_stream.jsonl"

_SELF = re.compile(r"\bmy\b|\bmyself\b|my own", re.IGNORECASE)


def _load(stream: Path, window: int) -> list[dict]:
    if not stream.exists():
        return []
    rows = []
    for ln in stream.read_text(encoding="utf-8", errors="replace").splitlines()[-window:]:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def score(stream: Path | None = None, window: int = 400) -> dict[str, Any]:
    """The correlate scorecard, all read from the real lived stream. Each score is 0..1."""
    rows = _load(stream if stream is not None else LIFE_STREAM, window)
    thoughts = [r for r in rows if r.get("kind") == "thought" and (r.get("meta") or {}).get("inner_voice")]
    n = len(thoughts)
    if n == 0:
        return {"n_moments": 0, "note": "no lived moments yet"}

    def frac(pred) -> float:
        return round(sum(1 for t in thoughts if pred(t.get("meta") or {})) / n, 3)

    # ignition: one broadcast per beat is structural (the loop records exactly one thought/beat);
    # measured here as the share of moments that are single workspace winners
    ignition = frac(lambda m: m.get("workspace") or m.get("inner_voice"))
    endogeneity = frac(lambda m: m.get("endogenous", True) is True)
    single_owner = frac(lambda m: m.get("mine") is True)
    temporal_depth = round(sum(int((t.get("meta") or {}).get("present_depth", 0)) for t in thoughts)
                           / n, 2)
    binding = frac(lambda m: m.get("percept_bound") is True or "feeling_tone" in m)
    # report accuracy: the stated feeling_tone must be consistent with the recorded hormones
    acc_ok = acc_n = 0
    for t in thoughts:
        m = t.get("meta") or {}
        tone = m.get("feeling_tone")
        cort = float((m.get("hormones") or {}).get("cortisol", 0.0))
        if tone is None:
            continue
        acc_n += 1
        # "under strain" must coincide with high cortisol; "at rest"/"even" with lower — a falsifiable
        # self-report check (Rosenthal's higher-order accuracy, operationalised)
        if (tone == "under strain") == (cort > 0.6):
            acc_ok += 1
        elif tone in ("even", "at rest", "quickened") and cort <= 0.6:
            acc_ok += 1
    report_accuracy = round(acc_ok / acc_n, 3) if acc_n else None
    # world-facing: curiosity/perception moments not about the self
    ext = [t for t in thoughts if (t.get("meta") or {}).get("source")
           in ("curiosity", "perception", "curious_search", "curious_browse")]
    world_facing = round(sum(1 for t in ext if not _SELF.search(t.get("content", ""))) / len(ext), 3) \
        if ext else 0.0

    return {
        "n_moments": n,
        "ignition": ignition,
        "endogeneity": endogeneity,
        "single_owner": single_owner,
        "temporal_depth": temporal_depth,
        "binding": binding,
        "report_accuracy": report_accuracy,
        "world_facing": world_facing,
        "discipline": ("structural correlates of inner life, measured; no claim that there is "
                       "something it is like to be ATANOR"),
    }
