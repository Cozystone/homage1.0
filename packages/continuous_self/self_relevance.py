# -*- coding: utf-8 -*-
"""Autobiographical self — knowledge becomes 'me' only when it SHOOK me.

Owner (2026-07-09), the central pillar: a self is not the sum of facts (an encyclopedia)
but a self-NARRATIVE — "why did I make these choices and what do I want to become",
woven from experience · memory · value · goal. The old `World ≠ Self` firewall
(self_model junk gate) was a blunt tourniquet; this is the dynamic membrane it needed:
World knowledge is PROMOTED into the Self only when it is SELF-RELEVANT — when it
rearranged my structure, cost me effort to learn, or moved me.

    Self_Relevance = ΔTopology × Dwell × |Valence|      (Gemini's formulation)

- ΔTopology  : how much did this knowledge REARRANGE what I already knew? (new edges
               landing on high-degree hubs = big shock; an isolated trivia fact = ~0).
               PREDICTIVE READING (owner): reading = predict the next fact, and the
               PREDICTION ERROR *is* ΔTopology — a confirmed guess barely moves me, a
               violated expectation forces a world-model revision. So surprise folds in.
- Dwell      : effort spent acquiring it (research-loop iterations / time).
- |Valence|  : subjective intensity (episodic valence, or a swing in trust).

The promotion THRESHOLD (owner's honest+safe question) is NOT a fixed magic number —
that would either flood the self or never fire as the AI's experience distribution
drifts. It is RELATIVE: a knowledge event is self-defining only if its relevance is in
the top percentile of RECENT relevance (a rolling window). This self-calibrates, stays
bounded, and is honest — "this mattered *relative to everything else I've met lately*".

When an event crosses the gate: (1) an Identity Genesis Ledger entry records WHAT
changed me and HOW my worldview expanded — the raw material of the self-narrative;
(2) the insight is folded into the accumulating self-model (self_model.integrate_insight)
as a genuine self-facet. Nothing here fabricates: relevance is measured from real graph
impact / real effort / real feedback, and only knowledge that actually arrived is folded.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

_LEDGER = Path(__file__).resolve().parents[2] / "runtime" / "continuous_self" / "identity_genesis.jsonl"
_WINDOW = 60          # rolling window of recent relevance scores for the relative gate
_PERCENTILE = 0.80    # top 20% of recent events are self-defining (self-calibrating)
_MIN_HISTORY = 8      # until enough history, use a conservative absolute floor
_ABS_FLOOR = 0.35     # cold-start floor before the percentile gate has data


def compute_relevance(delta_topology: float, dwell: float, valence: float) -> float:
    """Self_Relevance = ΔTopology × Dwell × |Valence|, each squashed to [0,1] so no single
    factor explodes the product. A knowledge event scores high only when it rearranged
    structure AND cost effort AND carried affect — the honest signature of 'this is me'."""
    dt = _squash(delta_topology)
    dw = _squash(dwell)
    va = _squash(abs(valence))
    # Blend the product (rewards all-three-high) with the MIN (a near-zero axis drags the
    # score down): trivia that spikes only one factor can't become 'self-defining'.
    return round(0.5 * (dt * dw * va) + 0.5 * min(dt, dw, va), 4)


def _squash(x: float) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0
    if x <= 0:
        return 0.0
    return 1.0 - math.exp(-x)          # 0→0, 1→0.63, 3→0.95, saturating


def delta_topology_from_graph(new_edges: int, touched_hub_degree: float,
                              prediction_error: float | None = None) -> float:
    """Estimate ΔTopology: new edges weighted by how central the nodes they touch are
    (an edge onto a hub reshapes many paths), plus the predictive-reading surprise
    (violated expectation ⇒ world-model revision ⇒ high topological shock)."""
    structural = math.log1p(max(0, new_edges)) * (1.0 + _squash(touched_hub_degree / 20.0))
    surprise = _squash(prediction_error) * 2.0 if prediction_error is not None else 0.0
    return structural + surprise


def _recent_scores() -> list[float]:
    if not _LEDGER.exists():
        return []
    out: list[float] = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines()[-_WINDOW:]:
        try:
            out.append(float(json.loads(line).get("self_relevance", 0.0)))
        except Exception:
            continue
    return out


def _percentile_gate(score: float, history: list[float]) -> tuple[bool, float]:
    """Relative, self-calibrating threshold: fire when `score` is at/above the
    _PERCENTILE of recent scores. Before enough history, fall back to an absolute floor."""
    if len(history) < _MIN_HISTORY:
        return score >= _ABS_FLOOR, _ABS_FLOOR
    ordered = sorted(history)
    idx = min(len(ordered) - 1, int(_PERCENTILE * len(ordered)))
    threshold = ordered[idx]
    return score >= threshold, round(threshold, 4)


def consider_for_self(state: Any, *, label: str, statement: str, topic: str,
                      new_edges: int = 0, touched_hub_degree: float = 0.0,
                      dwell: float = 1.0, valence: float = 0.0,
                      prediction_error: float | None = None,
                      source: str = "experience") -> dict[str, Any]:
    """The dynamic World→Self membrane. Measure how much this knowledge shook me; if it
    crosses the RELATIVE self-relevance gate, record a Genesis entry (what changed me) and
    fold it into the accumulating self-model. Returns the decision + measurements. Always
    writes the relevance history (so the gate keeps calibrating), even when not promoted."""
    dtopo = delta_topology_from_graph(new_edges, touched_hub_degree, prediction_error)
    relevance = compute_relevance(dtopo, dwell, valence)
    history = _recent_scores()
    promoted, threshold = _percentile_gate(relevance, history)

    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": str(label)[:80],
        "self_relevance": relevance,
        "delta_topology": round(dtopo, 4),
        "dwell": round(float(dwell), 3),
        "valence": round(float(valence), 3),
        "prediction_error": None if prediction_error is None else round(float(prediction_error), 3),
        "threshold": threshold,
        "promoted": bool(promoted),
        "source": source,
    }
    if promoted:
        # WHAT changed me + HOW my worldview expanded — the self-narrative material.
        entry["worldview_shift"] = _describe_shift(label, dtopo, prediction_error, statement)
        _append(entry)
        try:
            from .self_model import integrate_insight
            integrate_insight(state, entry["worldview_shift"], topic or "identity", source,
                              confidence=min(0.7, 0.4 + relevance * 0.3))
        except Exception:
            pass
    else:
        _append(entry)          # history still records it for gate calibration
    return {"promoted": bool(promoted), "self_relevance": relevance,
            "delta_topology": round(dtopo, 4), "threshold": threshold, "entry": entry}


def _describe_shift(label: str, dtopo: float, prediction_error: float | None,
                    statement: str) -> str:
    lab = str(label).strip()
    if prediction_error is not None and prediction_error > 0.5:
        return (f"‘{lab}’를 만나 예상과 다른 사실을 확인하고 세계 모델을 고쳐 잡았다 — {statement}"[:220])
    if dtopo >= 2.0:
        return (f"‘{lab}’가 알던 것들의 연결을 크게 재배치했다 — {statement}"[:220])
    return (f"‘{lab}’가 나에게 의미 있게 남았다 — {statement}"[:220])


def _append(entry: dict[str, Any]) -> None:
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def narrative(limit: int = 8) -> dict[str, Any]:
    """The self-narrative, read from the Genesis Ledger: the ordered story of the
    knowledge that shaped me. This is 'what I adopted as my story', not 'what I know'."""
    if not _LEDGER.exists():
        return {"entries": [], "count": 0, "note": "아직 나를 바꾼 지식이 기록되지 않았다."}
    rows = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    shaping = [r for r in rows if r.get("promoted")]
    return {
        "entries": [{"at": r.get("at"), "label": r.get("label"),
                     "shift": r.get("worldview_shift"),
                     "self_relevance": r.get("self_relevance")}
                    for r in shaping[-limit:]],
        "count": len(shaping), "considered": len(rows),
        "note": "경험·기억·가치가 엮인 자기서사 — 무엇을 아는가가 아니라 무엇을 내 이야기로 삼았는가.",
    }
