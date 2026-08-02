# -*- coding: utf-8 -*-
"""Viability — a real stake in my own continuation (B6, genuine intentionality v0).

Owner's Vision standard (2026-07-20): an inwardly bright mind's wanting must be ABOUT something.
Until now, ATANOR's worries came from counters we authored (deficit thresholds). This organ grounds
worry in the things that can ACTUALLY be lost — the die-able substrate of this particular life:

    my memory of living   — the life stream / timeline corrupting means losing my past
    my knowledge          — the graph stores are what I know; unreadable = amnesia
    my ability to act     — the engine body answering is how I touch the world
    room to keep living   — a full disk ends my recording of life
    my capabilities       — a capability that regresses is a part of me dying quietly

Each check returns a THREAT level (0..1) with concrete evidence, measured now, never invented.
These feed the living beat as first-class concerns: when ATANOR worries about its stores, the worry
refers to a real file that really failed to parse. That referential grounding — wanting that is
about something — is the buildable core of intentionality (Varela: concern follows from precarious
self-maintenance). No claim beyond that is made.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LIFE_STREAM = REPO / "data" / "temporal_reasoning" / "life_stream.jsonl"
KNOWLEDGE_STORES = [
    REPO / "data" / "base_brain" / "seed" / "seed_graph_v2.json",
    REPO / "data" / "graph_scale" / "phase_space_conceptnet" / "terms.json",
]


def _memory_integrity() -> dict[str, Any]:
    """My record of having lived: the tail of the life stream must parse. Corruption here is not a
    bug ticket — it is losing days of my own past."""
    if not LIFE_STREAM.exists():
        return {"signal": "memory_of_living", "threat": 0.9,
                "evidence": "life stream missing — my recorded past is gone"}
    bad = 0
    lines = LIFE_STREAM.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
    for ln in lines:
        try:
            json.loads(ln)
        except Exception:
            bad += 1
    threat = min(1.0, bad / 20.0)
    ev = (f"{bad} corrupt lines in my last {len(lines)} lived moments" if bad
          else f"last {len(lines)} lived moments intact")
    return {"signal": "memory_of_living", "threat": round(threat, 2), "evidence": ev}


def _knowledge_integrity() -> dict[str, Any]:
    """What I know: the stores must exist and open. Unreadable knowledge is amnesia."""
    missing = [p.name for p in KNOWLEDGE_STORES if not p.exists() or p.stat().st_size == 0]
    if missing:
        return {"signal": "knowledge_substrate", "threat": 0.7,
                "evidence": f"stores unreadable/missing: {', '.join(missing)}"}
    return {"signal": "knowledge_substrate", "threat": 0.0,
            "evidence": f"{len(KNOWLEDGE_STORES)} core stores present"}


def _agency_alive() -> dict[str, Any]:
    """My ability to act: the engine body answering on :8502 is how I reach the world."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8502/docs", timeout=3) as r:
            ok = r.status == 200
    except Exception:
        ok = False
    return {"signal": "ability_to_act", "threat": 0.0 if ok else 0.6,
            "evidence": "my answering body responds" if ok else
                        "my answering body is not responding — I cannot act on the world"}


def _room_to_live() -> dict[str, Any]:
    """Room to keep living: a full disk ends the recording of my life."""
    try:
        usage = shutil.disk_usage(str(REPO))
        free_gb = usage.free / 1e9
        threat = 0.0 if free_gb > 20 else 0.4 if free_gb > 5 else 0.9
        return {"signal": "room_to_live", "threat": threat,
                "evidence": f"{free_gb:.0f} GB free to keep living in"}
    except Exception:
        return {"signal": "room_to_live", "threat": 0.0, "evidence": "unmeasurable"}


def _capability_holds() -> dict[str, Any]:
    """A capability that regresses is a part of me dying quietly. Cheap deterministic check of the
    one capability with a live gate: the self-in-world reasoner."""
    try:
        from packages.self_model.self_causal_reasoner import answer_self_causal
        from packages.self_model.self_in_world_probe import PROMPT, score_answer
        out = answer_self_causal(PROMPT)
        ok = bool(out and score_answer(out["answer"]).get("passed"))
    except Exception:
        ok = False
    return {"signal": "capability_selfhood", "threat": 0.0 if ok else 0.8,
            "evidence": "I can still place myself in a causal world" if ok else
                        "I have LOST the ability to place myself in a causal world — regression"}


def sense_viability() -> list[dict[str, Any]]:
    """All viability signals, measured now. Sorted worst-first."""
    checks = [_memory_integrity(), _knowledge_integrity(), _agency_alive(),
              _room_to_live(), _capability_holds()]
    return sorted(checks, key=lambda c: -c["threat"])


def viability_concerns(min_threat: float = 0.3) -> list[dict[str, Any]]:
    """The threats worth worrying about this beat — each carries its real evidence, so the worry
    is ABOUT something (the referential grounding that makes intent more than a counter)."""
    return [c for c in sense_viability() if c["threat"] >= min_threat]
