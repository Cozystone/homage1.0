# -*- coding: utf-8 -*-
"""D3 — Curiosity Closure: the system's own gaps drive it to go learn. The deficit curriculum mined by sleep
(D1) becomes bounded expeditions; whatever the harvester brings back is gated (relevance to the deficit +
k-source consensus) before it is written to memory as a verified fact — which the next sleep consolidates
into the cortex. Gap → curiosity → gated harvest → memory → sleep → durable knowledge. Closed loop.

Hallucination-0 / anti-poison (the immune system that makes "let it loose on the web" safe): a claim is
accepted ONLY if it lexically ANCHORS the deficit topic (web-rescue relevance gate) AND is asserted by
≥ k DISTINCT sources (consensus-evidence machine). The harvester is INJECTABLE — the default is a safe stub;
the live searxng/structured-profile harvester is wired at deploy. No LLM.
"""
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from packages.reasoning_vm.live_memory import LiveMemory, _toks

# harvester(topic) -> list of {"text": str, "source": str} candidate facts
Harvester = Callable[[str], list[dict[str, Any]]]


def _null_harvester(topic: str) -> list[dict[str, Any]]:
    """Default: no live web. Inject a real harvester (searxng/structured_profile) at deploy."""
    return []


class CuriosityEngine:
    def __init__(self, memory: LiveMemory | None = None, harvester: Harvester = _null_harvester):
        self.mem = memory or LiveMemory()
        self.harvest = harvester

    def _gate(self, topic: str, candidates: list[dict[str, Any]], min_sources: int) -> list[dict[str, Any]]:
        """Two gates the poison must pass: (1) RELEVANCE — the claim must contain the deficit topic token,
        so an off-topic snippet cannot ride in; (2) CONSENSUS — ≥ min_sources DISTINCT sources assert the
        same normalized claim, so a single (possibly adversarial) page cannot inject a fact."""
        by_claim: dict[str, set[str]] = defaultdict(set)
        text_of: dict[str, str] = {}
        # A deficit topic is often several words ("Ada Lovelace", "boiling point"). Testing whether
        # the whole topic equals a single token rejected every one of them, so any multi-word gap was
        # unlearnable no matter what a harvester returned (measured 2026-07-28: 0 of 10 rows anchored
        # for "Ada Lovelace" while all 10 were on topic). Anchor on EVERY content token of the topic
        # instead — strictly stronger than the single-token test it replaces, never weaker.
        topic_tokens = {t.lower() for t in _toks(topic)}
        for c in candidates:
            text = str(c.get("text", ""))
            if not topic_tokens or not topic_tokens <= {t.lower() for t in _toks(text)}:
                continue                                                 # RELEVANCE gate (anchor the topic)
            key = " ".join(_toks(text))
            if not key:
                continue
            by_claim[key].add(str(c.get("source", "")))
            text_of[key] = text
        return [{"text": text_of[k], "sources": sorted(s)}
                for k, s in by_claim.items() if len(s) >= min_sources]    # CONSENSUS gate (k distinct)

    def pursue(self, topic: str, min_sources: int = 2) -> list[dict[str, Any]]:
        """One expedition: harvest the topic, gate, return the verified claims (not yet written)."""
        try:
            cands = self.harvest(topic) or []
        except Exception:
            cands = []
        return self._gate(topic, cands, min_sources)

    def run(self, deficits: list[dict[str, Any]], min_sources: int = 2, max_topics: int = 5,
            write: bool = True) -> dict[str, Any]:
        """Pursue the top deficits; write gated harvest to memory as verified=True (it passed relevance +
        consensus). The next sleep consolidates it into the cortex. Returns a curiosity report."""
        t0 = time.time()
        pursued, learned = [], 0
        seen: set[str] = set()                                            # dedup across overlapping topics
        for d in deficits[:max_topics]:
            topic = d.get("topic") if isinstance(d, dict) else str(d)
            claims = self.pursue(topic, min_sources=min_sources)
            accepted = 0
            for cl in claims:
                key = " ".join(_toks(cl["text"]))
                if key in seen:
                    continue
                seen.add(key)
                accepted += 1
                if write:
                    self.mem.remember(cl["text"], source="curiosity:" + ",".join(cl["sources"][:3]),
                                      verified=True)                       # passed the gate → trusted
                    learned += 1
            pursued.append({"topic": topic, "accepted": accepted})
        return {"topics_pursued": len(pursued), "facts_learned": learned, "detail": pursued,
                "min_sources": min_sources, "elapsed_s": round(time.time() - t0, 3)}
