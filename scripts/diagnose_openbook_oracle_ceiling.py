# -*- coding: utf-8 -*-
"""E6b oracle-ceiling diagnostic — how good could ANY overlap-family scorer possibly be?

Why this exists (2026-07-18). Three separate open-book levers were built and then reverted on
measurement: E5 (ContentIndex wiring), E5b (PMI on its intact co-occurrence table), E6b (ATANOR
Index disk BM25). Each time the pattern was identical — coverage went up, discrimination did not —
and each time we only learned that AFTER paying for a full cascade run. This script measures the
thing that should have been measured first: given the passage the retriever actually returns, is
the gold option even RECOVERABLE from it?

The metric is an ORACLE, deliberately generous to us:
  - it scores each option by the fraction of its distinctive content tokens present in the passage
  - it counts a win only when the GOLD option is UNIQUELY the best-covered
  - no threshold, no margin, no abstention: an oracle scorer that always picks the max

So it is an upper bound on every overlap-family scorer (_support, and _entail_score too, since the
latter's extra number/polarity/role-order signals only fire on sentences that already clear its 0.34
overlap gate). If this number sits below the 0.25 guess floor, no scorer improvement can rescue the
lane — the evidence is not in the text, and the honest move is to stop building retrieval levers.

Measured 2026-07-18 on MMLU-200 × wiki_en_full (7,016,505 EN passages):
    retrieval fired                    1.000   (BM25 always returns something)
    gold has ANY lexical presence      0.285
    gold UNIQUELY best-covered (top-1)  0.105   <- below the 0.25 chance floor
    same, raw BM25 (no title boost)     0.100   <- so the title rerank is NOT the culprit
    same, pooled oracle over top-5      0.160
    same, pooled oracle over top-10     0.165   <- saturates, still below chance
Conclusion: a structural ceiling for conceptual MCQ, not a ranking bug. See
docs/ATANOR_four_walls_research.md (E6b + CEILING FINDING).

Usage:  python scripts/diagnose_openbook_oracle_ceiling.py [slice.jsonl]
Plain MMLU is a DEV instrument here; the sealed north-star trio (KMMLU / MMLU-Pro / GPQA-Diamond)
is not touched by this script.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.reasoning_vm.openbook import (  # noqa: E402
    _EN_STOP, _STOP_CONTENT, _content, load_disk_index,
)

DEFAULT_SLICE = REPO / "data" / "benchmarks" / "mmlu" / "slice_25.jsonl"


def _toks(s: str) -> set[str]:
    """Distinctive content tokens of an option — the ones that could anchor it in a passage."""
    return {t for t in _content(s)
            if t not in _STOP_CONTENT and t not in _EN_STOP and len(t) >= 3}


def _cover(option: str, text_lower: str) -> float:
    o = _toks(option)
    return (sum(1 for t in o if t in text_lower) / len(o)) if o else 0.0


def _gold_uniquely_best(texts: list[str], choices: dict, gold: str) -> bool:
    """Oracle win: gold is strictly the best-covered option across the retrieved text(s)."""
    if not texts or gold not in choices:
        return False
    lows = [t.lower() for t in texts]
    cov = {k: max((_cover(v, tl) for tl in lows), default=0.0) for k, v in choices.items()}
    top = max(cov.values())
    return cov[gold] > 0 and cov[gold] == top and list(cov.values()).count(top) == 1


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SLICE
    if not path.exists():
        print(f"slice not found: {path}")
        return 1
    di = load_disk_index()
    if di is None:
        print("ATANOR Index not built — nothing to diagnose")
        return 1
    raw = di._idx
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    n = len(rows)
    print(f"slice={path.name}  n={n}  index={di.dir}")

    variants = {
        "top-1 (title-boost, shipped)":
            lambda q: [r["text"] for r in sorted(raw.search_topk(q, k=5),
                                                 key=lambda r: -r["score"])[:1]],
        "top-1 (raw BM25, no boost)":
            lambda q: [r["text"] for r in sorted(raw.search_topk(q, k=5),
                                                 key=lambda r: -r["bm25"])[:1]],
        "pooled oracle over top-5":
            lambda q: [r["text"] for r in raw.search_topk(q, k=5)],
        "pooled oracle over top-10":
            lambda q: [r["text"] for r in raw.search_topk(q, k=10)],
    }

    fired = present = 0
    for r in rows:
        got = di.search(r["question"])
        if not got:
            continue
        fired += 1
        if r.get("gold") in r.get("choices", {}) and _cover(r["choices"][r["gold"]], got[1].lower()) > 0:
            present += 1
    print(f"  retrieval fired                    {fired / n:.3f}")
    print(f"  gold has ANY lexical presence      {present / n:.3f}")

    for name, fn in variants.items():
        ok = 0
        for r in rows:
            try:
                texts = fn(r["question"])
            except Exception:
                texts = []
            if _gold_uniquely_best(texts, r.get("choices", {}), r.get("gold")):
                ok += 1
        flag = "  <-- BELOW CHANCE" if ok / n < 0.25 else ""
        print(f"  oracle: {name:32s} {ok / n:.3f}{flag}")
    print("  [chance floor = 0.25]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
