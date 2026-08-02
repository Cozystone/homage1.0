# -*- coding: utf-8 -*-
"""Next-FACT prediction — the honest hybrid that ends the dead-end forfeit.

Owner's third horizon (2026-07-09): " ?
 . ." An LLM
predicts P(next TOKEN) and hallucinates fluent ghosts. ATANOR instead predicts
P(next EDGE): given a subject, the trained phase geometry (RotatE — a relation is
a rotation, θ_s + r ≈ θ_o) proposes the most probable MISSING triple
[subject — predicate — object]. We do NOT promote it as truth. We MINT it as a
hypothesis, tagged source="predicted_hypothesis" with the model score, and the
realizer speaks it in HEDGED form (" … ").

The algebraic safety invariant is untouched: output ⊆ closure(facts ∪ rules).
The facts set simply now also contains honestly-labeled HYPOTHESIS facts, never
fabricated ones. The machine widens its territory of thought while always knowing
— and saying — that a guess is a guess. Confirmation only ever comes later, from
external evidence through the same gates (see hypothesis_minter.settle).

Honesty note on the number: the score is the phase-distance closeness in [0,1].
It is a MODEL signal, NOT a calibrated probability — we surface it labeled as
such and never dress a raw score up as '94% true'.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "predicted_hypotheses.jsonl"

_MIN_SCORE = 0.90       # closeness floor (random ≈ 0.36 on the 64-dim space)
_MIN_MARGIN = 0.10      # ...and stand out from the median object for that relation

# HONEST GATE (blind-lane doctrine, see [[learning-acceleration-derivation]]): even
# score-0.95 predictions are semantically garbage on the current coarse geometry
# ('juke is_a cooperation'). So the kernel is a candidate/observability TOOL, NOT
# auto-wired into user-facing answers until the phase space is retrained. engage
# checks this flag; the /intuition/predict endpoint still exposes it for inspection.
ENGAGE_ENABLED = False

# predicate -> hedged Korean realization (subject, object)
_KO_FRAME = {
    "is_a": "{s}은(는) {o}의 일종일 것으로 유추됩니다",
    "상위개념": "{s}은(는) {o}의 일종일 것으로 유추됩니다",
    "located_in": "{s}은(는) {o}에 위치할 것으로 유추됩니다",
    "소재지": "{s}은(는) {o}에 위치할 것으로 유추됩니다",
    "capital": "{s}의 수도는 {o}일 것으로 유추됩니다",
    "수도": "{s}의 수도는 {o}일 것으로 유추됩니다",
    "part_of": "{s}은(는) {o}의 일부일 것으로 유추됩니다",
    "used_for": "{s}은(는) {o}에 쓰일 것으로 유추됩니다",
    "country": "{s}은(는) {o}에 속할 것으로 유추됩니다",
    "국가": "{s}은(는) {o}에 속할 것으로 유추됩니다",
}


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _append(row: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_relations() -> tuple[Any, list[str]]:
    """The trained relation rotation vectors + their predicate names."""
    try:
        from .phase_space import _artifact_paths
        import numpy as np
        _p, rel_path, terms_path = _artifact_paths()
        if not rel_path.exists():
            return None, []
        rel = np.load(rel_path)
        data = json.loads(terms_path.read_text(encoding="utf-8"))
        preds = data.get("preds") or []
        if rel.ndim != 2 or len(preds) != rel.shape[0]:
            return None, []
        return rel.astype(np.float32), preds
    except Exception:
        return None, []


def _looks_mangled(term: str) -> bool:
    """Reject TermDict junk objects (OCR / tokenizer debris) from predictions:
    'gy mnasiu m', 'drive in nails' — isolated 1-char fragments or too many words."""
    parts = term.split()
    if len(parts) > 4:
        return True
    singles = sum(1 for p in parts if len(p) == 1 and p.isalpha())
    return singles >= 2


def _known_objects(store: Any, subject: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if store is None:
        return out
    try:
        for s, p, o in store.facts_about(subject, limit=80) or []:
            out.add((str(p), str(o)))
    except Exception:
        pass
    return out


def predict_missing_edges(subject: str, store: Any = None, k: int = 5,
                          min_score: float = _MIN_SCORE) -> list[dict[str, Any]]:
    """Predict the most probable MISSING (predicate, object) edges for a subject,
    using the trained phase geometry. Excludes edges the store already holds (that
    would be retrieval, not prediction). Returns ranked predictions; empty when
    the subject is unknown or nothing beats chance."""
    try:
        from .phase_space import _load, _SPACE
    except Exception:
        return []
    if not _load() or _SPACE.get("phases") is None:
        return []
    rel, preds = _load_relations()
    if rel is None:
        return []
    idx = _SPACE["idx"]
    ia = idx.get(subject)
    if ia is None:
        return []
    import numpy as np

    P = np.asarray(_SPACE["phases"], dtype=np.float32)
    # normalize by the ACTUAL phase width, not the DIM constant: the trained space
    # is 64-dim while phase_space.DIM defaults to 8, so 1 - d/8 mis-scaled every
    # score (d ranges [0, width]). Use the real width so the floor is meaningful.
    dim = P.shape[1]
    terms = _SPACE["terms"]
    known = _known_objects(store, subject)
    out: list[dict[str, Any]] = []
    for pr, pname in enumerate(preds):
        arg = (P[ia] + rel[pr] - P) / 2.0
        d = np.abs(np.sin(arg)).sum(axis=1)          # RotatE distance to every node
        med = float(np.median(d))
        order = np.argsort(d)
        for j in order[: k + 2]:
            jj = int(j)
            obj = terms[jj]
            if jj == ia or obj == subject or (pname, obj) in known or _looks_mangled(obj):
                continue
            score = round(1.0 - float(d[jj]) / dim, 4)      # closeness in [0,1]
            margin = round((med - float(d[jj])) / dim, 4)   # standout vs median
            if score < min_score or margin < _MIN_MARGIN:
                continue
            out.append({"subject": subject, "predicate": pname, "object": obj,
                        "model_score": score, "margin": margin})
            break                                            # one object per predicate
    out.sort(key=lambda r: -r["model_score"])
    return out[:k]


def realize_ko(pred: dict[str, Any]) -> str:
    s, p, o = pred["subject"], pred["predicate"], pred["object"]
    frame = _KO_FRAME.get(p)
    body = frame.format(s=s, o=o) if frame else f"{s}은(는) '{p}' 관계로 {o}와 이어질 것으로 유추됩니다"
    return "확인된 공식 근거는 없으나, 위상 기하학적 구조로 미루어 볼 때 " + body


def investigate(limit: int = 5) -> int:
    """Push unverified predicted hypotheses into the gated evidence queue as
    questions — the prediction only ASKS; the web-evidence gates answer. The
    kernel proposes a fact, the machine goes and checks it."""
    try:
        from . import abstain_queue
    except Exception:
        return 0
    pushed = 0
    for row in reversed(_rows()):
        if row.get("status") != "unverified":
            continue
        if abstain_queue.record_abstain(row.get("question", "")):
            pushed += 1
        if pushed >= limit:
            break
    return pushed


def _kg_has_edge(store: Any, s: str, p: str, o: str) -> bool:
    try:
        for a, b, c in store.facts_about(s, limit=80) or []:
            if str(b) == p and str(c) == o:
                return True
    except Exception:
        pass
    return False


def _age_days(minted_at: str) -> float:
    try:
        t = time.strptime(minted_at, "%Y-%m-%dT%H:%M:%S")
        return (time.time() - time.mktime(t)) / 86400.0
    except Exception:
        return 0.0


def settle(store: Any = None, max_age_days: float = 14.0) -> dict[str, int]:
    """Close the loop: a predicted hypothesis is CONFIRMED once the store holds
    the exact edge (evidence arrived and passed every gate); stale unverified
    ones RETIRE so guesses never accumulate. Nothing is promoted from here — a
    prediction only becomes knowledge through the evidence path, like everything
    else. Mirrors hypothesis_minter.settle."""
    if store is None:
        try:
            from .answer_bridge import _store
            store = _store()
        except Exception:
            return {"confirmed": 0, "retired": 0, "checked": 0}
    if store is None:
        return {"confirmed": 0, "retired": 0, "checked": 0}
    rows = _rows()
    confirmed = retired = checked = 0
    changed = False
    for row in rows:
        if row.get("status") != "unverified":
            continue
        checked += 1
        if _kg_has_edge(store, row.get("subject", ""), row.get("predicate", ""),
                        row.get("object", "")):
            row["status"] = "confirmed"
            row["confirmed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            confirmed += 1
            changed = True
        elif _age_days(row.get("minted_at", "")) > max_age_days:
            row["status"] = "retired"
            retired += 1
            changed = True
    if changed:
        LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                          encoding="utf-8")
    return {"confirmed": confirmed, "retired": retired, "checked": checked}


def mint_predicted_fact(subject: str, store: Any = None, language: str = "ko"
                        ) -> dict[str, Any] | None:
    """The kernel: predict the top missing edge, MINT it as a labeled hypothesis
    (never a fact), and return a hedged realization + its basis. DUAL-SPACE: prefer
    the CLEAN ConceptNet geometry (trustworthy enough to voice); fall back to the
    noisy store geometry only as an untrusted observation. Feeds the same evidence
    loop as hypothesis_minter. Returns None when nothing confident enough exists."""
    trusted = False
    preds: list[dict[str, Any]] = []
    try:
        from . import clean_space
        if clean_space.has(subject):
            known = _known_objects(store, subject)
            preds = clean_space.predict_edges(subject, k=3, known=known)
            trusted = bool(preds)          # a clean-space prediction is speakable
    except Exception:
        preds = []
    if not preds:
        preds = predict_missing_edges(subject, store=store, k=3)   # noisy fallback
    if not preds:
        return None
    top = preds[0]
    q = f"{top['subject']}은(는) {top['object']}와(과) '{top['predicate']}' 관계인가?"
    known = {(r.get("subject"), r.get("predicate"), r.get("object")) for r in _rows()}
    key = (top["subject"], top["predicate"], top["object"])
    if key not in known:
        _append({**top, "source": "predicted_hypothesis", "status": "unverified",
                 "question": q, "minted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    text = realize_ko(top) if language == "ko" else (
        f"No confirmed source, but the structure suggests {top['subject']} "
        f"—{top['predicate']}→ {top['object']}.")
    return {
        "text": text,
        "prediction": top,
        "alternatives": preds[1:],
        "source": "predicted_hypothesis",
        "hypothesis": True,
        "trusted": trusted,               # True = from the clean ConceptNet geometry
        "geometry": "conceptnet_clean" if trusted else "store_noisy",
        "note": "an honestly-labeled hypothesis (phase-space link prediction), "
                "not a confirmed fact; the score is an uncalibrated model signal",
    }
