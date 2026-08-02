# -*- coding: utf-8 -*-
"""Learned discourse model v0 — the (flesh) of +, learned from real prose.

The composer's connectives were a fixed tuple applied in fixed order ( →
 → ), which is why composed paragraphs read mechanical. This model
learns HOW REAL KOREAN SENTENCES chain from the corpus the store already holds
(attributed evidence sentences + full definitional objects — human-written
prose), and the composer consults it for connective choice.

The honesty contract is unchanged and testable: the output vocabulary stays
CLOSED — a connective may only be emitted if it is BOTH observed in the corpus
AND on the approved whitelist below. Learning chooses among approved tokens;
it can never introduce a new one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STATS_PATH = REPO / "data" / "grounded_composer" / "discourse_stats.json"

# the closed, approved connective vocabulary (superset of the old fixed tuple).
# Learning RANKS these from data; it cannot go outside the list. The rhetorical


APPROVED_MARKERS = ("또한", "그리고", "한편", "이와 함께", "특히", "더불어", "아울러", "이어서",
                    "그래서", "이 때문에", "즉", "결국", "하지만", "그러나", "예를 들어",
                    "왜냐하면")

_STATS: dict[str, Any] = {"freq": None, "mtime": 0.0}


def learn_discourse_stats(store: Any, max_rows: int = 50_000,
                          log: Any = print) -> dict[str, Any]:
    """Count sentence-initial marker usage + marker->marker transitions over the
    store's real prose (evidence + long defined_as objects). Saves stats JSON."""
    freq: dict[str, int] = {m: 0 for m in APPROVED_MARKERS}
    trans: dict[str, dict[str, int]] = {m: {n: 0 for n in APPROVED_MARKERS}
                                        for m in APPROVED_MARKERS}
    scanned = 0
    try:
        cols = store.open_columns()
        p_col, o_col = cols["p"], cols["o"]
        want_pids = set()
        for pname in ("evidence", "defined_as"):
            pid = store.terms.lookup(pname)
            if pid is not None:
                want_pids.add(pid)
        import numpy as np

        pc = np.asarray(p_col[:])
        idxs = np.nonzero(np.isin(pc, np.array(sorted(want_pids), dtype=pc.dtype)))[0]
        for i in idxs[:max_rows].tolist():
            text = store.terms.term(int(o_col[i]))
            if len(text) < 40:  # short heads carry no discourse structure
                continue
            scanned += 1
            prev = None
            for sent in re.split(r"(?<=다\.)\s+|(?<=[.!?])\s+", text):
                sent = sent.strip()
                head = None
                for m in APPROVED_MARKERS:
                    # clause-initial OR clause-internal usage both count — the
                    # store's prose is mostly single sentences, where connectives

                    if sent.startswith(m) or f" {m} " in sent or f", {m}" in sent:
                        head = m
                        freq[m] += 1
                if head:
                    if prev:
                        trans[prev][head] += 1
                prev = head
    except Exception as e:  # pragma: no cover - store variability
        log(f"  discourse stats: scan stopped ({type(e).__name__})")
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps({"freq": freq, "trans": trans,
                                      "scanned": scanned}, ensure_ascii=False),
                          encoding="utf-8")
    _STATS["freq"] = None
    log(f"  discourse stats: {scanned} prose rows, marker counts {freq}")
    return {"scanned": scanned, "freq": freq}


def _load() -> dict[str, Any] | None:
    try:
        if not STATS_PATH.exists():
            return None
        mtime = STATS_PATH.stat().st_mtime
        if _STATS["freq"] is None or _STATS["mtime"] != mtime:
            data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
            _STATS["freq"] = data.get("freq") or {}
            _STATS["trans"] = data.get("trans") or {}
            _STATS["mtime"] = mtime
        return _STATS
    except Exception:
        return None


def pick_connective(index: int, prev: str | None = None) -> str | None:
    """Deterministic learned choice for the index-th continuation sentence.
    Ranks approved markers by corpus frequency (transition-aware when prev is
    known), avoids immediate repetition, rotates down the rank list so long
    answers vary naturally. None when no stats exist (caller keeps its default)."""
    stats = _load()
    if not stats or not stats.get("freq"):
        return None
    freq = stats["freq"]
    if prev and stats.get("trans", {}).get(prev):
        scored = dict(stats["trans"][prev])
        # transition counts are sparse — blend with global frequency
        for m, c in freq.items():
            scored[m] = scored.get(m, 0) * 3 + c
    else:
        scored = dict(freq)
    ranked = [m for m, c in sorted(scored.items(), key=lambda kv: -kv[1])
              if m in APPROVED_MARKERS and c > 0]
    if not ranked:
        return None
    pool = [m for m in ranked if m != prev] or ranked
    return pool[index % len(pool)]
