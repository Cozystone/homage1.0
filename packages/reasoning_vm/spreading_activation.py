# -*- coding: utf-8 -*-
""" L3 — (Collins&Loftus 1975). ·· , ()
 . " ?" 
'' ' ' — ANALOGIZED ( , " 
 ~ ") . . (UNKNOWN).

 · , . No LLM."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional


class SpreadingActivation:
    def __init__(self, decay: float = 0.5, threshold: float = 0.012):
        self.adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.decay = decay
        self.threshold = threshold

    def add_edge(self, a: str, b: str, w: float = 1.0) -> None:
        """ ( ). ."""
        self._bump(a, b, w); self._bump(b, a, w)

    def _bump(self, a: str, b: str, w: float) -> None:
        for i, (n, ww) in enumerate(self.adj[a]):
            if n == b:
                self.adj[a][i] = (b, ww + w)
                return
        self.adj[a].append((b, w))

    def activate(self, cue: str, max_steps: int = 3) -> dict[str, float]:
        """ . node → ( ). ."""
        energy: dict[str, float] = defaultdict(float)
        frontier = {cue: 1.0}
        for _ in range(max_steps):
            nxt: dict[str, float] = defaultdict(float)
            for node, e in frontier.items():
                deg = sum(w for _, w in self.adj[node]) or 1.0
                for nb, w in self.adj[node]:
                    spread = e * self.decay * (w / deg)
                    if spread >= self.threshold:
                        nxt[nb] += spread
            if not nxt:
                break
            for n, e in nxt.items():
                if n != cue:
                    energy[n] += e
            frontier = dict(nxt)
        return dict(energy)

    def related(self, cue: str, k: int = 5) -> list[tuple[str, float]]:
        return sorted(self.activate(cue).items(), key=lambda kv: kv[1], reverse=True)[:k]


def build_assoc_from_facts(facts: dict, isa: dict) -> SpreadingActivation:
    """L1 /isa : (s—o) + (child—parent) ."""
    sa = SpreadingActivation()
    for (s, _p), rec in facts.items():
        sa.add_edge(s, rec["o"], 1.0)
    for child, parents in isa.items():
        for par in parents:
            sa.add_edge(child, par, 1.2)
    return sa
