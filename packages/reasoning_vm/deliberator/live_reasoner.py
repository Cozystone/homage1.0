# -*- coding: utf-8 -*-
"""LiveReasoner — the bridge from Layer A live memory to the DELIBERATOR reader. Teach a fact this moment
(a write to the content index, zero gradient steps) and reason over it the next: recall the relevant live
passages, then run the learned multi-hop reader (relevance rank → span extract) over them. This is what a
chat surface calls so a fact the user just stated becomes usable evidence without retraining.

Hallucination-0: recall respects the verified gate; every answer carries the provenance + verified status
of the evidence it used, and an empty answer is returned (never fabricated) when nothing is recalled. No LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.reasoning_vm.live_memory import STORE, LiveMemory


class LiveReasoner:
    def __init__(self, ckpt: str = "ace_hotpot.pt", store: Path | None = None):
        from packages.reasoning_vm.deliberator.planner import MultiHopReader
        self.mem = LiveMemory(path=store or STORE)
        self.reader = MultiHopReader(ckpt=ckpt)

    def learn(self, fact: str, source: str = "", verified: bool = False) -> dict[str, Any]:
        """Write a fact — retrievable immediately, untrusted by default (only the gate promotes it)."""
        return self.mem.remember(fact, source=source, verified=verified)

    def ask(self, question: str, k: int = 4, include_unverified: bool = True) -> dict[str, Any]:
        """Recall live evidence, then read the answer off it. grounded=False (empty answer) when the
        memory has nothing relevant — the honest abstention, never a guess."""
        hits = self.mem.recall(question, k=k, include_unverified=include_unverified)
        if not hits:
            return {"answer": "", "support": [], "evidence": [], "grounded": False}
        paras = [((h["source"] or f"mem{i}"), h["text"]) for i, h in enumerate(hits)]
        out = self.reader.answer(question, paras, k=min(2, len(paras)), chain=False, rank="ans")
        return {"answer": out["answer"], "support": out["support"], "evidence": hits,
                "grounded": bool(out["answer"]),
                "unverified_used": any(not h["verified"] for h in hits[:2])}
