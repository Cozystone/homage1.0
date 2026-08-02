# -*- coding: utf-8 -*-
"""Value stack → endogenous curriculum (Phase 3-4).

The mind decides WHAT to learn next from its own measured state — never from a
schedule or a hand-written topic table. Candidate topics come only from real
signals; each is scored on the value stack and the ranked winners are pushed
into the abstain queue, where the existing gated ingest machinery ( /
search API / judge gate) does the actual learning.

Value stack (weights sum to 1; every score cites its evidence):
 * grounding_gap 0.4 — real users asked and the engine abstained (flywheel
 failures). The strongest claim on attention.
 * user_relevance 0.3 — the topic touches the user deep model (possessions,
 habits, preferences): learning serves THIS user.
 * curiosity 0.2 — the topic appears in the selfhood daemon's own open
 question (endogenous inquiry pressure, 3-3).
 * novelty 0.1 — the KG holds nothing on it yet (a lookup miss).

Nothing here fabricates a topic: no signal, no curriculum.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
CURRICULUM_PATH = _REPO / "data" / "curriculum" / "curriculum.jsonl"

_WEIGHTS = {"grounding_gap": 0.4, "user_relevance": 0.3, "curiosity": 0.2, "novelty": 0.1}

_STOP = {"뭐", "무엇", "어떻게", "왜", "누구", "언제", "어디", "그리고", "그럼", "이거", "저거",
         "그거", "대해", "대해서", "알아", "몰라", "설명", "말해", "해줘", "좀", "너", "나",
         "the", "a", "an", "is", "are", "what", "how", "why", "who"}


def _content_terms(text: str) -> list[str]:
    toks = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", str(text or ""))
    return [t for t in toks if t not in _STOP][:6]


def _failure_terms(limit: int = 300) -> dict[str, int]:
    """Terms from REAL failed/abstained turns (flywheel), with counts."""
    counts: dict[str, int] = {}
    try:
        from packages.flywheel.logger import FAILURES_PATH

        if not FAILURES_PATH.exists():
            return counts
        rows = FAILURES_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
        for line in rows:
            try:
                row = json.loads(line)
            except Exception:
                continue
            for t in _content_terms(row.get("question") or ""):
                counts[t] = counts.get(t, 0) + 1
    except Exception:
        pass
    return counts


def _user_terms() -> set[str]:
    """Terms the user's deep model actually contains (evidence-backed)."""
    out: set[str] = set()
    try:
        from packages.user_model import derive_user_model

        m = derive_user_model()
        for p in m.get("possessions") or []:
            out.update(_content_terms(p.get("object") or ""))
        for h in m.get("habits") or []:
            out.update(_content_terms(h.get("object") or ""))
        for p in m.get("preferences") or []:
            out.update(_content_terms(p.get("value") or ""))
    except Exception:
        pass
    return out


def _self_question_terms() -> set[str]:
    """Terms in the selfhood daemon's CURRENT open question — live endogenous
    curiosity, read from the running mind (empty when it sleeps)."""
    try:
        from app.routers.continuous_self import _SELF  # type: ignore

        if _SELF.running:
            snap = _SELF.snapshot()
            return set(_content_terms(str(snap.get("self_question") or "")))
    except Exception:
        pass
    return set()


def _kg_has(term: str) -> bool:
    try:
        from packages.graph_scale.answer_bridge import _store

        kg = _store()
        if kg is None:
            return False
        return bool(kg.facts_with_sources(term, limit=1))
    except Exception:
        return False


def build_curriculum(limit: int = 8) -> list[dict[str, Any]]:
    """Rank candidate topics on the value stack. Every entry carries its scores
    and the signals behind them — the curriculum is auditable."""
    failures = _failure_terms()
    if not failures:
        return []  # no real gap signal -> no curriculum (never invent topics)
    user_terms = _user_terms()
    self_terms = _self_question_terms()
    max_fail = max(failures.values())

    ranked: list[dict[str, Any]] = []
    for term, n_fail in failures.items():
        scores = {
            "grounding_gap": n_fail / max_fail,
            "user_relevance": 1.0 if term in user_terms else 0.0,
            "curiosity": 1.0 if term in self_terms else 0.0,
            "novelty": 0.0 if _kg_has(term) else 1.0,
        }
        total = sum(_WEIGHTS[k] * v for k, v in scores.items())
        ranked.append({
            "term": term, "value": round(total, 4), "scores": scores,
            "evidence": {"failed_turns": n_fail,
                         "user_model_hit": term in user_terms,
                         "self_question_hit": term in self_terms},
        })
    ranked.sort(key=lambda r: r["value"], reverse=True)
    return ranked[:limit]


def enqueue_top(limit: int = 3, log: Any = print) -> dict[str, Any]:
    """Push the top-ranked topics into the abstain queue (the gated ingest lane)
    and append the decision to the curriculum ledger. Bounded per call."""
    curriculum = build_curriculum(limit=limit)
    pushed: list[str] = []
    if curriculum:
        try:
            from packages.graph_scale import abstain_queue

            for row in curriculum:
                added = abstain_queue.record_abstain(row["term"])
                if added:
                    pushed.extend(added)
        except Exception as exc:
            log(f"curriculum enqueue failed: {exc}")
    CURRICULUM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CURRICULUM_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ranked": curriculum, "pushed": pushed,
        }, ensure_ascii=False) + "\n")
    return {"ranked": len(curriculum), "pushed": len(pushed), "topics": pushed}
