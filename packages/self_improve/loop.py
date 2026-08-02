# -*- coding: utf-8 -*-
"""Self-improvement loop — ATANOR runs its whole benchmark battery, finds its OWN worst weaknesses,
searches freely to understand them, and routes any concrete fix through the constitution. The
owner's directive (2026-07-20): "모든 벤치마크를 수행하면 부족한 점을 찾아서 스스로 검색하여 자가개선."

This is the CLOSED LOOP composed from pieces already built this project:
  measure (every battery)  ->  rank weaknesses (question_miner, residual-first)
    ->  self-search (advisor_session: local ollama free, or the web intake)
    ->  candidate intake (patch_intake: constitution guard, advice_only if no concrete patch)
    ->  verify gate (auto_self_modification: staging tests + no sealed-gate regression)  ->  journal.

Honesty is built in, not asserted:
  - Weaknesses come from real metric files; the loop is silent if the batteries are perfect.
  - The GENERATE step is the current bottleneck: ATANOR cannot author code yet (authorship 0.000),
    so most cycles end 'advice_only / 0 applied'. That number is reported truthfully and is exactly
    what the code-mastery curriculum raises. Like bAbI at 0.127, the loop starts honest and low.
  - Nothing auto-applies without the constitution: a fix touching the moral core / any gate is
    refused at intake; a surviving candidate still faces staging + no-regression.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_improve" / "cycles.jsonl"

from packages.advisor_loop.patch_intake import intake
from packages.advisor_loop.question_miner import Question, mine


@dataclass
class Weakness:
    topic: str
    residual: float
    metric_source: str
    question: str


@dataclass
class CycleReport:
    ts: float
    weaknesses: list[dict] = field(default_factory=list)
    searched: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    applied: int = 0
    summary: str = ""


def find_weaknesses(top_k: int = 5) -> list[Weakness]:
    """Rank the system's measured residuals, information-dense first (question_miner generalized)."""
    return [Weakness(topic=q.topic, residual=q.residual, metric_source=q.metric_source,
                     question=q.text) for q in mine(max_questions=top_k)]


def run_cycle(search_fn: Callable[[Question], str] | None = None, top_k: int = 3,
              apply_fn: Callable[[list[str]], bool] | None = None) -> CycleReport:
    """One self-improvement cycle. search_fn(question)->advice text (default: no search, record the
    query only — the caller wires ollama/web). apply_fn(paths)->bool verifies+applies a survivor
    (default: None => never auto-applies, honest report only)."""
    rep = CycleReport(ts=0.0)          # ts stamped by the caller (Date.now unavailable in some ctx)
    weaknesses = find_weaknesses(top_k)
    rep.weaknesses = [w.__dict__ for w in weaknesses]
    for w in weaknesses:
        q = Question(topic=w.topic, text=w.question, metric_source=w.metric_source,
                     residual=w.residual)
        if search_fn is not None:
            advice = search_fn(q)
            rep.searched.append({"topic": w.topic, "advice_chars": len(advice or "")})
            cand = intake("self-improve", advice or "", summary=f"self-search on {w.topic}")
            rep.candidates.append({"topic": w.topic, "status": cand.status,
                                   "paths": cand.paths, "reason": cand.reason})
            if cand.status == "candidate" and apply_fn is not None and apply_fn(cand.paths):
                rep.applied += 1
        else:
            rep.searched.append({"topic": w.topic, "advice_chars": 0, "note": "search not wired"})
    rep.summary = (f"{len(weaknesses)} weaknesses ranked; "
                   f"{sum(1 for c in rep.candidates if c['status'] == 'candidate')} concrete "
                   f"candidate(s); {rep.applied} applied (0 expected until code-authorship matures)")
    return rep


def journal(rep: CycleReport, now_utc: float) -> None:
    rep.ts = now_utc
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rep.__dict__, ensure_ascii=False) + "\n")
