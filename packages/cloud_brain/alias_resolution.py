"""Alias / entity resolution — the surface-form split fix ( 1).

The consensus machine counts evidence per canonical (subject|relation|object) key.
If "" and "Nvidia" are different strings, the SAME fact's evidence splits
across surface forms and consensus starves. Resolution is two conservative layers,
both data-driven (no hand alias tables):

 1. NORMALIZATION — NFKC, casefold, whitespace/middle-dot removal. Merges
 "Nvidia"/"nvidia"/" "/"". Deterministic, reversible.
 2. LEARNED PAIRS — Korean encyclopedic text writes aliases inline:
 " (Nvidia Corporation) …". Every parenthetical of that
 shape is a real, sourced alias pair; we record it (append-only JSONL) and
 union-find the pairs into clusters. NOTHING is merged by substring or
 similarity — and stay distinct unless a source says otherwise.

resolve(label) returns the cluster representative, so ledger keys computed
through the resolver merge retroactively when the ledger replays its events.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

_PAREN = re.compile(r"([0-9A-Za-z가-힣··][0-9A-Za-z가-힣··\s]{1,39})\(([^()]{2,60})\)")
_DATEISH = re.compile(r"\d{2,4}\s*년|~|\d{1,2}\s*월|\d{1,2}\s*일")
_WS = re.compile(r"[\s··]+")


def normalize(label: str) -> str:
    s = unicodedata.normalize("NFKC", str(label or "")).casefold().strip()
    return _WS.sub("", s)


class AliasResolver:
    """Union-find over normalized labels, persisted as append-only pair events."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._parent: dict[str, str] = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    pair = json.loads(line)
                    self._union(normalize(pair["a"]), normalize(pair["b"]))
                except (json.JSONDecodeError, KeyError):
                    continue

    # ---- union-find ----
    def _find(self, x: str) -> str:
        root = x
        while self._parent.get(root, root) != root:
            root = self._parent[root]
        while self._parent.get(x, x) != x:  # path compression
            self._parent[x], x = root, self._parent[x]
        return root

    def _union(self, a: str, b: str) -> None:
        if not a or not b:
            return
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            # deterministic representative: lexicographically smallest survives
            keep, drop = sorted([ra, rb])
            self._parent[drop] = keep

    # ---- public API ----
    def resolve(self, label: str) -> str:
        return self._find(normalize(label))

    def add_pair(self, a: str, b: str, *, persist: bool = True) -> bool:
        na, nb = normalize(a), normalize(b)
        if not na or not nb or na == nb or self._find(na) == self._find(nb):
            return False
        self._union(na, nb)
        if persist and self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"a": a, "b": b}, ensure_ascii=False) + "\n")
        return True

    def learn_from_sentence(self, text: str) -> int:
        """Harvest 'X(Y)' alias pairs from one sentence. Date parentheticals
 ('(1992 ~ )') are rejected — they are lifespans, not aliases."""
        learned = 0
        for m in _PAREN.finditer(str(text or "")):
            left, right = m.group(1).strip(), m.group(2).strip()
            if _DATEISH.search(right) or _DATEISH.search(left):
                continue
            if len(normalize(left)) < 2 or len(normalize(right)) < 2:
                continue
            if self.add_pair(left, right):
                learned += 1
        return learned
