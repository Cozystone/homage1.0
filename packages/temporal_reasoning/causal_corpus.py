# -*- coding: utf-8 -*-
"""Causal corpus — mine ACTION → OUTCOME order pairs from records of what humans did and what
happened next, and feed the learned temporal-causal field.

Owner's commission (2026-07-20): GDELT (history-as-events) + EM-DAT (disasters) + incident
postmortems (software failures) are exactly "인간 사회가 어떤 행동을 했고 어떤 결과가 나왔는가" —
the action→outcome corpus the temporal-causal physics has been starving for (its measured wall was
the ABSENCE of description-pair data). Two miners here, one contract:

  1. INCIDENT/POSTMORTEM timelines — the gold register. A postmortem's timeline section is literally
     'HH:MM event' lines in true order ('14:02 deploy started; 14:09 error rate rose; 14:31
     rollback'). mine_incident_timeline() reads those clock-stamped lines and emits ordered event-
     token pairs with REAL order evidence.
  2. GDELT 15-minute export slices (free/open) — world events with dates and CAMEO action codes.
     mine_gdelt_slice() orders same-actor events across days into (earlier, later) pairs.

Everything lands in a QUARANTINED side store (causal_counts.json) — same shape as the existing
order/web counts, merged into the PrecedenceField only through the usual retrain path, never a
silent production write. Pairs are counted evidence, not asserted facts; downstream use stays
hypothesis-flagged (block_universe)."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "temporal_reasoning" / "causal_counts.json"

_TIME_LINE = re.compile(r"^\s*(?:[*\-–]\s*)?(\d{1,2}):(\d{2})(?::\d{2})?\s*(?:UTC|GMT|PT|ET|KST)?\s*[-–—:]?\s*(.+)$")
_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_STOP = {"the", "and", "was", "were", "with", "from", "that", "this", "have", "has", "had",
         "for", "are", "our", "their", "its", "than", "then", "into", "been", "will"}


def _event_tokens(text: str, k: int = 3) -> list[str]:
    """The k most contentful tokens of one timeline line — the event's lexical signature."""
    toks = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
    return toks[:k]


# ---------------------------------------------------------------- 1) postmortem timelines
def mine_incident_timeline(text: str) -> list[tuple[str, str]]:
    """Clock-stamped incident-timeline lines -> ordered (earlier_token, later_token) pairs.
    Order is read off the REAL clock stamps, so every pair is genuine order evidence. Midnight
    rollover: a time earlier than its predecessor starts a new day (kept monotone)."""
    events: list[tuple[int, list[str]]] = []
    day = 0
    prev_min = -1
    for line in (text or "").splitlines():
        m = _TIME_LINE.match(line.strip())
        if not m:
            continue
        minutes = int(m.group(1)) * 60 + int(m.group(2))
        if minutes < prev_min:                        # crossed midnight
            day += 1
        prev_min = minutes
        toks = _event_tokens(m.group(3))
        if toks:
            events.append((day * 1440 + minutes, toks))
    pairs: list[tuple[str, str]] = []
    for (ta, a), (tb, b) in zip(events, events[1:]):
        if tb <= ta:
            continue
        for x in a:
            for y in b:
                if x != y:
                    pairs.append((x, y))
    return pairs


# ---------------------------------------------------------------- 2) GDELT slices
def mine_gdelt_slice(zip_bytes: bytes, max_rows: int = 50000) -> list[tuple[str, str]]:
    """A GDELT v2 export slice (CSV in a zip): order same-actor events by date into pairs of their
    CAMEO action descriptions. Actions are the EventCode root names — closed vocabulary, no prose."""
    # CAMEO root code -> action word (public codebook, factual labels)
    cameo = {"01": "statement", "02": "appeal", "03": "intent", "04": "consult", "05": "diplomacy",
             "06": "cooperate", "07": "aid", "08": "yield", "09": "investigate", "10": "demand",
             "11": "disapprove", "12": "reject", "13": "threaten", "14": "protest", "15": "force",
             "16": "coerce", "17": "assault", "18": "fight", "19": "conflict", "20": "violence"}
    by_actor: dict[str, list[tuple[float, str]]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = zf.namelist()[0]
        reader = csv.reader(io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace"),
                            delimiter="\t")
        for i, row in enumerate(reader):
            if i >= max_rows or len(row) < 30:
                continue
            # GDELT 2.0 export schema: col 4 = FractionDate (float year, sub-day resolution) -> orders
            # same-day events (col 1 SQLDATE was day-only and collapsed a slice to one instant); col 6
            # = Actor1Name, col 16 = Actor2Name, col 26 = EventCode.
            actor, code = row[6] or row[16], row[26]
            try:
                when = float(row[4])
            except (ValueError, IndexError):
                continue
            act = cameo.get((code or "")[:2])
            if actor and act:
                by_actor.setdefault(actor, []).append((when, act))
    pairs: list[tuple[str, str]] = []
    for seq in by_actor.values():
        seq.sort()
        for (da, a), (db, b) in zip(seq, seq[1:]):
            if db >= da and a != b:                    # later-or-equal instant, different action
                pairs.append((a, b))
    return pairs


# ---------------------------------------------------------------- quarantined store + field feed
def feed(pairs: list[tuple[str, str]], source: str) -> dict:
    """Count pairs into the QUARANTINED causal store (never a direct production write). Returns the
    updated totals. The PrecedenceField consumes this only via an explicit retrain call."""
    counts: Counter = Counter()
    if STORE.exists():
        try:
            counts.update({tuple(k.split("|", 1)): v
                           for k, v in json.loads(STORE.read_text(encoding="utf-8"))["pairs"].items()})
        except Exception:
            pass
    for a, b in pairs:
        counts[(a, b)] += 1
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({
        "pairs": {f"{a}|{b}": c for (a, b), c in counts.items()},
        "note": f"QUARANTINED order evidence (last source: {source}); consumed only via field retrain",
    }, ensure_ascii=False), encoding="utf-8")
    return {"new_pairs": len(pairs), "total_distinct": len(counts),
            "total_evidence": sum(counts.values())}


def retrain_field_with_causal(min_count: int = 2):
    """Merge the quarantined causal counts into a fresh PrecedenceField fit (explicit, auditable).
    Returns the new field WITHOUT overwriting the production artifact — caller decides promotion."""
    from .precedence_field import PrecedenceField
    if not STORE.exists():
        return None
    data = json.loads(STORE.read_text(encoding="utf-8"))["pairs"]
    counts = Counter({tuple(k.split("|", 1)): v for k, v in data.items() if v >= min_count})
    if not counts:
        return None
    return PrecedenceField.fit(counts)


def _causal_pairs(min_count: int = 2) -> dict[tuple[str, str], int]:
    """The mined DIRECTED pair evidence (typed causal edges) from the quarantined store:
    (earlier, later) -> observed count. Raw data lookup — nothing authored. {} if no store yet."""
    if not STORE.exists():
        return {}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))["pairs"]
    except Exception:
        return {}
    out: dict[tuple[str, str], int] = {}
    for k, v in data.items():
        if v >= min_count and "|" in k:
            a, b = k.split("|", 1)
            out[(a, b)] = v
    return out


def merged_field(min_count: int = 2):
    """The production precedence field OVERLAID with the clean causal field: for a token the causal
    corpus has learned (action verbs from GDELT/postmortems), its cleaner phase wins; everything else
    keeps the broad-vocabulary production phase. This is the MESH — the 4D reasoner gets broad reach
    AND clean action-causality, instead of either alone. Read-only compose; production stays intact.

    Two dominance mechanisms make the clean causal field WIN over the noisy broad 1-D phase (the
    measured ~0% fire cause was the broad field's register-pollution and undifferentiated phase):
      1. register-pollution markup (MARKUP_STOP: quot/ref/amp/page/article/user/…) is dropped from
         the field entirely, so it can never be surfaced as an event or bias a phase mean;
      2. the causal action tokens are marked as the field's ``event_vocab`` — the ONLY tokens
         block_universe surfaces as next/prev events — and the mined directed pair counts ride along
         as ``causal_pairs`` so a projection walks the REAL learned successor, not the phase-nearest.
    Returns the (cleaned) production field if there is no causal store yet — still fail-closed, just
    without the causal dominance layer."""
    from .precedence_field import PrecedenceField, MARKUP_STOP
    prod = PrecedenceField.load()
    causal = retrain_field_with_causal(min_count)
    pairs = _causal_pairs(min_count)

    def _strip_markup(phase: dict, seen: dict):
        p = {t: v for t, v in phase.items() if t not in MARKUP_STOP}
        s = {t: seen.get(t, 0) for t in p}
        return p, s

    if prod is None:
        if causal is None:
            return None
        phase, seen = _strip_markup(causal.phase, causal.seen)
        return PrecedenceField(phase, seen, event_vocab=set(phase), causal_pairs=pairs)
    if causal is None:
        phase, seen = _strip_markup(prod.phase, prod.seen)        # cleaned, but no causal dominance layer
        return PrecedenceField(phase, seen)

    phase, seen = _strip_markup(prod.phase, prod.seen)
    # rescale causal phases into the production phase range so the overlay is comparable, then
    # override — the causal field is small and clean, the production field broad and noisy.
    pv = list(phase.values())
    lo, hi = (min(pv), max(pv)) if pv else (-1.0, 1.0)
    cv = list(causal.phase.values())
    clo, chi = (min(cv), max(cv)) if cv else (-1.0, 1.0)
    span = (chi - clo) or 1.0
    event_vocab: set[str] = set()
    for tok, ph in causal.phase.items():
        if tok in MARKUP_STOP:
            continue
        phase[tok] = lo + (ph - clo) / span * (hi - lo)      # map causal range onto production range
        seen[tok] = seen.get(tok, 0) + causal.seen.get(tok, 0)
        event_vocab.add(tok)                                  # the clean vocabulary that DOMINATES surfacing
    return PrecedenceField(phase, seen, event_vocab=event_vocab, causal_pairs=pairs)
