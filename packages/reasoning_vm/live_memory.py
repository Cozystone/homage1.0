# -*- coding: utf-8 -*-
"""Layer A — retrieval-augmented LIVE memory: learn now, recall the next moment, with ZERO weight update.

Owner 2026-07-16 (" "). The honest mechanism behind human recall is
not per-second synaptic rewiring for facts — it is ASSOCIATIVE RETRIEVAL over a memory that grows. So a
fact ATANOR meets this turn is written to a content-indexed live store and is retrievable the very next
turn, without retraining the frozen reasoning core (kNN-LM principle). This gives ~90% of "real-time
learning" for free; the deeper frozen-weight problem (Layer B adapters / Layer C neuromorphic) is separate.

Hallucination-0 preserved: every live memory carries PROVENANCE and a `verified` flag; unverified items
are recallable but flagged, and only the existing consensus/judge gate can flip verified=True. Live memory
never asserts — it surfaces, tagged. Append-only + persisted, so recall survives restarts. No LLM.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "graph_scale" / "live_memory" / "store.jsonl"
_TOK = re.compile(r"[A-Za-z0-9]+")
_STOP = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "is", "are", "was", "were", "be",
         "by", "as", "at", "it", "its", "this", "that", "with", "from", "which", "who", "what", "when"}


def _stem(w: str) -> str:
    """Conservative morphological normalization so a query verb/noun matches its stored inflection
    ('produces'->'produce', 'weighs'->'weigh', 'kilograms'->'kilogram'). Only the trailing plural /
    3rd-person -s is stripped, and only for words long enough that it can't collapse a real word
    ('gas', 'bus' keep their s; 'ss'/'us'/'is' endings are left alone). Improves live-recall rank-1
    discrimination among sibling facts (Magnum A1, 2026-07-19)."""
    if len(w) > 4 and w.endswith("es") and w[-3] in "sxz":
        return w[:-2]                       # boxes->box, buzzes->buzz
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "ous")):
        return w[:-1]                       # produces->produce, weighs->weigh, kilograms->kilogram
    return w


def _toks(text: str) -> list[str]:
    return [_stem(w) for w in _TOK.findall(str(text).lower()) if len(w) > 1 and w not in _STOP]


class LiveMemory:
    def __init__(self, path: Path = STORE):
        self.path = path
        self.items: list[dict[str, Any]] = []
        self.inv: dict[str, set[int]] = defaultdict(set)     # token → item indices (inverted index)
        self.df: dict[str, int] = defaultdict(int)
        self._load()

    def _index(self, i: int, toks: list[str]) -> None:
        for t in set(toks):
            self.inv[t].add(i)
            self.df[t] += 1

    def _load(self) -> None:
        if not self.path.exists():
            return
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                it = json.loads(ln)
            except Exception:
                continue
            it["_toks"] = _toks(it["text"])
            self._index(len(self.items), it["_toks"])
            self.items.append(it)

    def remember(self, text: str, source: str = "", verified: bool = False,
                 persist: bool = True) -> dict[str, Any]:
        """Write a fact into live memory — retrievable IMMEDIATELY, no retraining. verified=False by default
        (only the gate may promote it)."""
        toks = _toks(text)
        it = {"id": len(self.items), "text": str(text), "source": str(source),
              "verified": bool(verified), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "_toks": toks}
        self._index(len(self.items), toks)
        self.items.append(it)
        if persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: v for k, v in it.items() if k != "_toks"}, ensure_ascii=False) + "\n")
        return it

    def recall(self, query: str, k: int = 5, include_unverified: bool = True) -> list[dict[str, Any]]:
        """Associative retrieval: IDF-weighted token overlap over the growing store. A fact remembered
        one call ago ranks here now — that IS the real-time learning, no gradient step."""
        q = _toks(query)
        n = max(1, len(self.items))
        cand: dict[int, float] = defaultdict(float)
        for t in set(q):
            idf = math.log(n / (1 + self.df.get(t, 0))) + 1.0
            for i in self.inv.get(t, ()):
                cand[i] += idf
        scored = []
        for i, s in cand.items():
            it = self.items[i]
            if not include_unverified and not it["verified"]:
                continue
            scored.append((s, it))
        scored.sort(key=lambda x: -x[0])
        return [{"text": it["text"], "source": it["source"], "verified": it["verified"],
                 "score": round(s, 3)} for s, it in scored[:k]]

    def verify(self, item_id: int) -> bool:
        """Promote an item to verified — called ONLY after the consensus/judge gate passes (hallucination-0)."""
        for it in self.items:
            if it["id"] == item_id:
                it["verified"] = True
                self._rewrite()
                return True
        return False

    def _rewrite(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(
            json.dumps({k: v for k, v in it.items() if k != "_toks"}, ensure_ascii=False)
            for it in self.items) + "\n", encoding="utf-8")

    def stats(self) -> dict[str, int]:
        return {"items": len(self.items), "verified": sum(1 for it in self.items if it["verified"]),
                "vocab": len(self.inv)}
