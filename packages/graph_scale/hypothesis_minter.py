# -*- coding: utf-8 -*-
"""Hypothesis minting — self-refinement stage 3, the CLOSED loop.

Gemini's stage 3 with the one correction that keeps us honest: internal
mathematical consistency NEVER registers knowledge. A hypothesis is a
QUESTION the system asks itself; only external evidence, through the same
gates as everything else, can promote it.

The loop (all pieces already exist — this module closes the circuit):
 1. MINT — trained phase space finds cross-domain pairs that resonate
 strongly yet share NO direct KG edge: structure suggesting an
 unrecorded relation ("A B 
 ").
 2. LEDGER — the pair lands in data/graph_scale/hypotheses.jsonl with
 status=unverified, its resonance, and the shared relational
 context that made it interesting. Never touches the store.
 3. INVESTIGATE — the top hypotheses feed the abstain/curriculum queue as
 questions; the existing web learner gathers evidence through
 every gate (consensus, judge, quarantine).
 4. SETTLE — a later pass re-checks: if the KG now HOLDS a direct edge for
 the pair (evidence arrived and passed), the hypothesis is
 marked confirmed; still-unsupported ones age out. The system
 widened its own map, and every new edge is source-backed.

Model-collapse immunity is exactly here: the generative layer only ever emits
QUESTIONS into the verification machine, never facts into the substrate.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "hypotheses.jsonl"

_MINT_RESONANCE = 0.72   # strong-resonance floor for an interesting pair
_MAX_PER_RUN = 6


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _append(row: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _kg_edge_between(store: Any, a: str, b: str) -> str | None:
    """A direct edge (either direction) between two terms, if the KG holds one."""
    try:
        for f in store.facts_about(a, limit=60) or []:
            if str(f[2]) == b:
                return str(f[1])
        for f in store.facts_about(b, limit=60) or []:
            if str(f[2]) == a:
                return str(f[1])
    except Exception:
        pass
    return None


def mint(store: Any = None, k_terms: int = 60, seed: int | None = None) -> list[dict[str, Any]]:
    """Find strongly-resonant, KG-unconnected cross-domain pairs and ledger
    them as unverified hypotheses. Returns the newly minted rows."""
    try:
        from .phase_space import _load, _SPACE, neighbors
    except Exception:
        return []
    if not _load():
        return []
    if store is None:
        try:
            from .answer_bridge import _store

            store = _store()
        except Exception:
            store = None
    if store is None:
        return []

    import numpy as np

    rng = np.random.default_rng(seed if seed is not None else int(time.time()) % 100_000)
    terms = _SPACE["terms"]
    ko = [t for t in terms if any("가" <= c <= "힣" for c in t) and 2 <= len(t) <= 8]
    if len(ko) < 2:
        return []
    sample = rng.choice(len(ko), size=min(k_terms, len(ko)), replace=False)
    known = {(r.get("a"), r.get("b")) for r in _rows()}

    minted: list[dict[str, Any]] = []
    for i in sample:
        a = ko[int(i)]
        for b, res in neighbors(a, k=6):
            if res < _MINT_RESONANCE or b == a:
                continue
            if a[:2] == b[:2] or a in b or b in a:  # same-family: not cross-domain
                continue
            pair = tuple(sorted((a, b)))
            if (pair[0], pair[1]) in known:
                continue
            if _kg_edge_between(store, a, b):
                continue  # the KG already knows why they resonate
            row = {
                "a": pair[0], "b": pair[1], "resonance": round(res, 4),
                "status": "unverified",
                "question": f"{pair[0]}와 {pair[1]}은 어떤 관계인가",
                "minted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _append(row)
            known.add((pair[0], pair[1]))
            minted.append(row)
            if len(minted) >= _MAX_PER_RUN:
                return minted
    return minted


def investigate(limit: int = 3) -> int:
    """Push the freshest unverified hypotheses into the gated learning queue —
    the mint only ever asks; the web-evidence machinery answers."""
    pushed = 0
    try:
        from . import abstain_queue
    except Exception:
        return 0
    for row in reversed(_rows()):
        if row.get("status") != "unverified":
            continue
        if abstain_queue.record_abstain(row["question"]):
            pushed += 1
        if pushed >= limit:
            break
    return pushed


def settle(store: Any = None) -> dict[str, int]:
    """Re-check unverified hypotheses against the KG: evidence that arrived
    (and passed the gates) confirms them; nothing is promoted from here."""
    if store is None:
        try:
            from .answer_bridge import _store

            store = _store()
        except Exception:
            return {"confirmed": 0, "checked": 0}
    if store is None:
        return {"confirmed": 0, "checked": 0}
    rows = _rows()
    confirmed = checked = 0
    changed = False
    for row in rows:
        if row.get("status") != "unverified":
            continue
        checked += 1
        edge = _kg_edge_between(store, row["a"], row["b"])
        if edge:
            row["status"] = "confirmed"
            row["edge"] = edge
            row["confirmed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            confirmed += 1
            changed = True
    if changed:
        LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                          encoding="utf-8")
    return {"confirmed": confirmed, "checked": checked}
