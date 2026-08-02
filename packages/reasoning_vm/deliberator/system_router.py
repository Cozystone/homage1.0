# -*- coding: utf-8 -*-
"""D2 — System-1 / System-2 promotion router. The brain is efficient (~20W) partly because it defaults to
fast associative answers and only pays for slow deliberation when it must. Here: answer from the single
best evidence (S1, cheap) when ONE paragraph covers the question; escalate to multi-evidence reasoning
(S2, more reader passes) only when the question's content is SPLIT across paragraphs — the signature of a
genuine multi-hop question.

The escalation signal is CALIBRATED LEXICAL COVERAGE, not the neural relevance head (which is saturated at
~1.0 and cannot threshold). max single-paragraph coverage of the question's content tokens: high → one hop
suffices (S1); low → the answer needs stitching (S2). No LLM.
"""
from __future__ import annotations

from packages.reasoning_vm.live_memory import _toks


class SystemRouter:
    def __init__(self, reader, cover_threshold: float = 0.6, k_slow: int = 3):
        self.reader = reader
        self.cover_threshold = cover_threshold      # one para covering ≥ this of the question → single-hop
        self.k_slow = k_slow

    def _max_cover(self, question: str, paragraphs) -> float:
        q = set(_toks(question))
        if not q:
            return 1.0
        return max((len(q & set(_toks(t))) / len(q) for _title, t in paragraphs), default=0.0)

    def answer(self, question: str, paragraphs) -> dict:
        """S1 by default; escalate to S2 only when no single paragraph covers the question."""
        if not paragraphs:
            return {"answer": "", "support": [], "system": "S1", "escalated": False}
        cover = self._max_cover(question, paragraphs)
        if cover >= self.cover_threshold:                       # SYSTEM 1 — fast, single best evidence
            out = self.reader.answer(question, paragraphs, k=1, chain=False, rank="ans")
            out["system"] = "S1"
            out["escalated"] = False
        else:                                                   # SYSTEM 2 — deliberate over more evidence
            out = self.reader.answer(question, paragraphs, k=self.k_slow, chain=False, rank="ans")
            out["system"] = "S2"
            out["escalated"] = True
        out["cover"] = round(float(cover), 3)
        return out
