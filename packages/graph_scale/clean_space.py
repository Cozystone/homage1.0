# -*- coding: utf-8 -*-
"""Clean phase space — the ConceptNet-trained geometry for REASONING quality.

The dual-space architecture (proven 2026-07-09): the broad store geometry has
coverage but is semantically noisy (trained on bulk is_a); the ConceptNet-trained
geometry is clean but narrower. So we keep BOTH — the store space for broad
retrieval/priming, and this clean space for the quality-sensitive reasoning
features (next-fact prediction, topology veto). A prediction from the clean space
is trustworthy enough to speak; one from the noisy store is not (kept gated).

Loads data/graph_scale/phase_space_conceptnet/ (built from the ConceptNet dump via
gpu_phase_space.train_from_triples). Read-only, mmap'd, no production impact.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

_DIR = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "phase_space_conceptnet"
_S: dict[str, Any] = {"phases": None, "rel": None, "terms": None, "idx": None,
                      "preds": None, "mtime": 0.0}


def _load() -> bool:
    try:
        ph = _DIR / "phases.npy"
        if not ph.exists():
            return False
        key = ph.stat().st_mtime
        if _S["phases"] is None or _S["mtime"] != key:
            _S["phases"] = np.load(ph, mmap_mode="r")
            _S["rel"] = np.load(_DIR / "relations.npy")
            data = json.loads((_DIR / "terms.json").read_text(encoding="utf-8"))
            _S["terms"] = data["terms"]
            _S["preds"] = data.get("preds", [])
            _S["idx"] = {t: i for i, t in enumerate(data["terms"])}
            _S["mtime"] = key
        return True
    except Exception:
        return False


def available() -> bool:
    return _load()


def has(term: str) -> bool:
    return _load() and term in _S["idx"]


def neighbors(term: str, k: int = 8) -> list[tuple[str, float]]:
    if not _load():
        return []
    i = _S["idx"].get(term)
    if i is None:
        return []
    ph = np.asarray(_S["phases"])
    sims = np.cos(ph - ph[i]).mean(axis=1)
    order = np.argsort(-sims)
    out = []
    for j in order[: k + 1]:
        if int(j) != i:
            out.append((_S["terms"][int(j)], round(float(sims[int(j)]), 3)))
        if len(out) >= k:
            break
    return out


def predict_edges(subject: str, k: int = 5, min_score: float = 0.80,
                  known: set[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """Predict the most probable MISSING (predicate, object) edges for a subject on
    the CLEAN geometry — quality good enough to voice as a hedged hypothesis.
    Returns ranked predictions with a calibrated (phase-width-normalized) score."""
    if not _load() or _S["idx"].get(subject) is None:
        return []
    ia = _S["idx"][subject]
    P = np.asarray(_S["phases"], dtype=np.float32)
    rel, preds = _S["rel"], _S["preds"]
    dim = P.shape[1]
    known = known or set()
    out: list[dict[str, Any]] = []
    for pr, pname in enumerate(preds):
        d = np.abs(np.sin((P[ia] + rel[pr] - P) / 2.0)).sum(axis=1)
        order = np.argsort(d)
        for j in order[: k + 2]:
            jj = int(j)
            obj = _S["terms"][jj]
            if jj == ia or obj == subject or (pname, obj) in known:
                continue
            score = round(1.0 - float(d[jj]) / dim, 4)
            if score < min_score:
                continue
            out.append({"subject": subject, "predicate": pname, "object": obj,
                        "model_score": score, "space": "conceptnet_clean"})
            break
    out.sort(key=lambda r: -r["model_score"])
    return out[:k]


def resonance(a: str, b: str) -> float | None:
    if not _load():
        return None
    ia, ib = _S["idx"].get(a), _S["idx"].get(b)
    if ia is None or ib is None:
        return None
    return float(np.cos(_S["phases"][ia] - _S["phases"][ib]).mean())


def analogy(a: str, b: str, c: str, k: int = 5) -> list[tuple[str, float]]:
    """A:B :: C:X on the clean geometry — the A→B relation IS a rotation in RotatE
    space, so X is whatever lands nearest to C rotated by (B−A). Pure learned
    geometry: no relation table, no candidate list; unknown terms return []."""
    if not _load():
        return []
    idx = _S["idx"]
    ia, ib, ic = idx.get(a), idx.get(b), idx.get(c)
    if ia is None or ib is None or ic is None:
        return []
    P = np.asarray(_S["phases"], dtype=np.float32)
    dim = P.shape[1]
    target = P[ic] + (P[ib] - P[ia])
    d = np.abs(np.sin((target - P) / 2.0)).sum(axis=1)
    order = np.argsort(d)
    out: list[tuple[str, float]] = []
    for j in order:
        jj = int(j)
        t = _S["terms"][jj]
        if t in (a, b, c):
            continue
        out.append((t, round(1.0 - float(d[jj]) / dim, 4)))
        if len(out) >= k:
            break
    return out
