# -*- coding: utf-8 -*-
"""Intuition lane — the System 1 spark (stochastic phase-space perturbation).

Kahneman's two systems: we finished System 2 (the reasoning VM + the Surgeon —
strict algebraic verification). This is the missing System 1: the intuitive,
associative PROPOSER that leaps.

A HONEST engineering correction to the naive "inject Gaussian noise" idea:
independent noise on phase vectors DECORRELATES concepts (pushes resonance to 0);
it cannot make two far vectors align — that needs 8 dims to cancel at once, ~0
probability. So a random storm just yields mush, never a meeting. The mechanism
that actually leaps is the RELATIONAL LENS (RotatE-native): displace a concept
along a real, LEARNED relation direction (θ_a + r) and see which distant concept
it lands on. The displacement is grounded (a direction the graph actually
learned), energy scales its magnitude, and a small jitter makes it stochastic:

 anchor a ──(energy · learned relation direction + jitter)──► a lensed point
 │ │
 │ the nearest REAL concept b to that point is "a seen b, often
 │ through relation r" — grounded, yet often cross-domain. from a far
 ▼ ▼ domain
 [ System 2: Surgeon + reasoning VM ] ◄── every spark is a QUESTION, never a fact

At energy 0 there is no displacement, so b is just a's own neighbour and the
far-filter rejects it: a calm mind makes no wild leaps. Turn energy up and the
lens reaches further, into other domains — inspiration waxing with arousal.

The invariant that separates us from an LLM given a temperature knob: an LLM's
whole model is fog, so noise makes it hallucinate CONFIDENT WRONG FACTS. ATANOR's
spark only ever emits a HYPOTHESIS (" A B ?") into the
verification machine. Nothing reaches the substrate without external evidence
passing the same gates as everything else. So we can let the machine go
beautifully mad — the safety is structural. ", ."

energy = the system's cognitive/affective state (feed it the digital-hormone
arousal level to make inspiration wax and wane like a person's). Higher energy =
wider noise = wilder, more distant leaps.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "sparks.jsonl"

_CLEAN_MAX = 0.20    # a and b must be FAR in the clean geometry (a true leap)
_LAND_MIN = 0.40     # ...yet the lensed point must land genuinely NEAR b
_JITTER = 0.30       # stochastic jitter (radians) on the lens at energy=1.0
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


def _kg_edge(store: Any, a: str, b: str) -> bool:
    try:
        for f in store.facts_about(a, limit=40) or []:
            if str(f[2]) == b:
                return True
        for f in store.facts_about(b, limit=40) or []:
            if str(f[2]) == a:
                return True
    except Exception:
        pass
    return False


def _type_leap(store: Any, a: str, b: str) -> str:
    """The Surgeon's verdict, REPURPOSED: for an is_a claim a cross-family pair is
 contamination; for an ANALOGY it is the whole point. So we label, never
 reject — a hard type gap is the juiciest metaphor ( ↔ )."""
    try:
        from .surgeon import inspect
        v = inspect(store, a, b)
        if isinstance(v, dict) and v.get("contaminated"):
            return "pure_type_leap"     # strongly different families — great metaphor
        return "near_domain"
    except Exception:
        return "unknown"


def _relation_lenses(rng: Any, terms: list[str]) -> Any:
    """The creative operators: learned relation DIRECTIONS to view a concept
    through. Prefer the trained relation vectors; else derive emergent directions
    from random concept-pair differences (analogical transfer). Returns (L, dim)."""
    import numpy as np
    try:
        from .phase_space import _artifact_paths
        _p, rel_path, _t = _artifact_paths()
        if rel_path.exists():
            rel = np.load(rel_path)
            if rel.ndim == 2 and len(rel) >= 1:
                return rel.astype(np.float32)
    except Exception:
        pass
    return None  # caller falls back to pair-difference lenses


def spark(store: Any = None, energy: float = 0.5, k_terms: int = 80,
          seed: int | None = None) -> list[dict[str, Any]]:
    """Displace concepts along learned relation directions (scaled by energy) and
    surface the distant concepts they land on — grounded cross-domain leaps. Each
    is ledgered as an unverified QUESTION (never a fact). Returns the new sparks."""
    try:
        from .phase_space import _load, _SPACE
    except Exception:
        return []
    if not _load() or _SPACE.get("phases") is None:
        return []
    if store is None:
        try:
            from .answer_bridge import _store
            store = _store()
        except Exception:
            store = None

    import numpy as np

    rng = np.random.default_rng(seed if seed is not None else int(time.time()) % 100_000)
    terms = _SPACE["terms"]
    P = np.asarray(_SPACE["phases"], dtype=np.float32)
    N, dim = P.shape
    ko_idx = np.array([i for i, t in enumerate(terms)
                       if any("가" <= c <= "힣" for c in t) and 2 <= len(t) <= 8])
    if len(ko_idx) < 3:
        return []

    lenses = _relation_lenses(rng, terms)
    if lenses is None or lenses.shape[1] != dim:
        # emergent lenses: differences between random concept pairs (a→b directions)
        pa = P[rng.choice(N, size=64)]
        pb = P[rng.choice(N, size=64)]
        lenses = (pb - pa).astype(np.float32)

    anchors = rng.choice(len(ko_idx), size=min(k_terms, len(ko_idx)), replace=False)
    known = {(r.get("a"), r.get("b")) for r in _rows()}
    minted: list[dict[str, Any]] = []
    scale = max(0.0, min(1.5, energy))
    for ai in anchors:
        a_glob = int(ko_idx[ai])
        pa = P[a_glob]
        lens = lenses[rng.integers(len(lenses))]
        jitter = rng.normal(0.0, _JITTER, size=dim).astype(np.float32)
        target = pa + scale * (lens + jitter)              # the lensed point
        land = np.cos(P - target).mean(axis=1)             # resonance to every concept
        clean = np.cos(P - pa).mean(axis=1)                # clean resonance to anchor
        # a genuine leap: lands near b, yet b is FAR from a in the clean geometry
        cand = np.nonzero((land > _LAND_MIN) & (clean < _CLEAN_MAX))[0]
        if len(cand) == 0:
            continue
        for bi in cand[np.argsort(-land[cand])]:
            b_glob = int(bi)
            a, b = terms[a_glob], terms[b_glob]
            if a == b or a in b or b in a:
                continue
            pair = tuple(sorted((a, b)))
            if pair in known:
                continue
            if store is not None and _kg_edge(store, a, b):
                continue                                   # the KG already links them
            leap = _type_leap(store, a, b) if store is not None else "unknown"
            row = {
                "a": pair[0], "b": pair[1],
                "clean_resonance": round(float(clean[b_glob]), 4),
                "sparked_resonance": round(float(land[b_glob]), 4),
                "energy": round(float(energy), 3),
                "leap": leap,
                "status": "unverified",
                "kind": "intuition_spark",
                "question": f"{pair[0]}와(과) {pair[1]}은(는) 무엇이 닮았는가?",
                "minted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _append(row)
            known.add(pair)
            minted.append(row)
            break                                          # one spark per anchor
        if len(minted) >= _MAX_PER_RUN:
            break
    return minted


def energy_from_hormones(hormones: dict[str, Any] | None) -> float:
    """Map the digital-hormone state to spark energy, so inspiration waxes and
    wanes like a person's: curiosity/arrival (dopamine, noradrenaline) widen the
    leaps; stress and forced rest (cortisol, repair) calm them. Baseline 0.2 —
    a mind at rest still muses a little. Range [0, 1.2]."""
    h = hormones or {}
    try:
        arousal = 0.6 * float(h.get("noradrenaline", 0.0)) + 0.5 * float(h.get("dopamine", 0.0))
        damp = 0.5 * float(h.get("cortisol", 0.0)) + 0.7 * float(h.get("repair", 0.0))
    except Exception:
        return 0.5
    return round(max(0.0, min(1.2, 0.2 + arousal - damp)), 3)


def collide(store: Any, term_a: str, term_b: str, k_bridges: int = 6) -> dict[str, Any]:
    """FORCE two named concepts from different domains to meet, and observe the
    machine's proposed connective tissue: the concepts that resonate with BOTH
    (the shared ground of the analogy). The pair is ledgered as a QUESTION, never
    a fact. This is 'collide two domains and watch the first spark', directed."""
    try:
        from .phase_space import _load, _SPACE
    except Exception:
        return {"available": False, "reason": "no_phase_space"}
    if not _load() or _SPACE.get("phases") is None:
        return {"available": False, "reason": "phase_space_untrained"}
    import numpy as np

    idx = _SPACE["idx"]
    ia, ib = idx.get(term_a), idx.get(term_b)
    if ia is None or ib is None:
        missing = [t for t, i in ((term_a, ia), (term_b, ib)) if i is None]
        return {"available": False, "reason": "concept_not_in_space", "missing": missing}
    P = np.asarray(_SPACE["phases"], dtype=np.float32)
    terms = _SPACE["terms"]
    res_a = np.cos(P - P[ia]).mean(axis=1)
    res_b = np.cos(P - P[ib]).mean(axis=1)
    both = np.minimum(res_a, res_b)                 # a bridge must resonate with BOTH
    both[ia] = both[ib] = -2.0
    order = np.argsort(-both)
    bridges = []
    for j in order[: k_bridges * 3]:
        t = terms[int(j)]
        if t in (term_a, term_b) or term_a in t or term_b in t:
            continue
        bridges.append({"term": t, "res_a": round(float(res_a[j]), 3),
                        "res_b": round(float(res_b[j]), 3)})
        if len(bridges) >= k_bridges:
            break
    q = f"{term_a}와(과) {term_b}은(는) 무엇이 닮았는가?"
    _append({"a": term_a, "b": term_b,
             "clean_resonance": round(float(res_a[ib]), 4),
             "kind": "forced_collision", "status": "unverified", "question": q,
             "bridges": [b["term"] for b in bridges],
             "minted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"available": True, "a": term_a, "b": term_b,
            "clean_resonance": round(float(res_a[ib]), 4),
            "bridges": bridges, "question": q,
            "note": "a QUESTION (analogy to investigate), never asserted as fact"}


def investigate(limit: int = 3) -> int:
    """Feed the freshest sparks to the gated evidence machine as questions — the
    spark only ASKS; the web-evidence gates answer. Never writes facts."""
    try:
        from . import abstain_queue
    except Exception:
        return 0
    pushed = 0
    for row in reversed(_rows()):
        if row.get("status") != "unverified":
            continue
        if abstain_queue.record_abstain(row["question"]):
            pushed += 1
        if pushed >= limit:
            break
    return pushed


def recent(limit: int = 20) -> list[dict[str, Any]]:
    return _rows()[-limit:]
