# -*- coding: utf-8 -*-
"""Close the Generative Leap Loop — LeapEngine (proposer) → the SAME verify gate everything else uses.

Owner 2026-07-15 (ultimate goal, AGI): " … ." The LeapEngine
(leap.py) is the System-1 proposer: latent-algebra intuition + graph structure-transfer. This module is
the wire that makes its proposals real WITHOUT ever letting them touch the substrate as facts:

 LeapEngine.transfer(source, target) → triple-shaped Conjectures (target, r, x')
 │ [because the source domain has (source, r, x)]
 ▼
 hypothesis ledger (data/graph_scale/hypotheses.jsonl, status=unverified, source="leap")
 │ ← the SAME ledger hypothesis_minter uses, so its investigate()/settle() gates
 ▼ already handle the rest of the loop. No new verification path is invented.
 investigate() → the conjecture becomes a QUESTION in the gated web-evidence queue
 ▼
 settle() → only if external evidence later puts a real edge in the KG is it 'confirmed'

Doctrine (BINDING, [[generative-leap-loop]] [[atanor-final-plan-charter]]): the generator is prolific and
fallible on purpose (BVSR — vary widely, select strictly); NOTHING here is asserted; internal resonance
never registers knowledge; only source-backed evidence through the existing gates can confirm a leap.
No LLM. This is the selector half of "LLMs have intuition without verification; we have verification."
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

# Relations to skip: LEXICAL/generic ones carry no world-structure to transfer (aliasing "thompson"→
# "smith" is a naming fact, not a discovery). A source is "interesting" for analogy only when it
# participates in a SPECIFIC world relation (orbits, part_of, causes, located_in, capable_of…).
_GENERIC = {"antonym", "synonym", "defined_as", "related_to", "is_a", "instance_of",
            "subclass_of", "type", "hypernym", "hyponym", "also", "see_also",
            "alias", "abbreviation", "acronym", "nickname", "formerly", "also_known_as", "spelling"}


def _facts_fn(store: Any, limit: int = 40) -> Callable[[str], list]:
    def fa(e: str) -> list:
        try:
            return list(store.facts_about(e, limit=limit) or [])
        except Exception:
            return []
    return fa


def _specific_relations(edges: list) -> set[str]:
    return {str(r) for (_s, r, _o) in edges if str(r) not in _GENERIC}


def _pick_target(engine, source: str, src_edges: list, k: int = 25):
    """A cross-domain analogue of `source`: an embedding neighbour that is NOT the same surface family,
    shares NO direct edge, yet has its own relational structure to receive the transfer. Gentner's
    structure-mapping wants a DISTANT domain — surface-near but relationally-populated."""
    src_objs = {str(o) for (_s, _r, o) in src_edges} | {source}
    for t, _sim in engine._nn(engine.emb.embed(source), k, exclude={source}):
        if t in src_objs or source in t or t in source or t[:3] == source[:3]:
            continue                                   # same family / trivially related — not a leap
        tgt_edges = engine.fa(t) if engine.fa else []
        if len(tgt_edges) < 2:
            continue                                   # nothing to map onto
        if any(str(o) == source for (_s, _r, o) in tgt_edges):
            continue                                   # already directly linked
        return t, tgt_edges
    return None, []


def mint_leaps(store: Any = None, emb: Any = None, *, n_sources: int = 60, per_source: int = 2,
               max_mint: int = 8, seed: int | None = None) -> list[dict[str, Any]]:
    """Run the LeapEngine over the live store and LEDGER its best structure-transfer conjectures as
    unverified hypotheses (never facts). Returns the newly minted rows. Reuses hypothesis_minter's
    ledger + de-dup so a leap and a resonance-mint can never double-register the same pair."""
    from .leap import LeapEngine
    from . import learned_discriminator as LD
    from packages.graph_scale import hypothesis_minter as HM

    if emb is None:
        emb = LD.Embeddings.load(LD._DIR)
    if emb is None:
        return []
    if store is None:
        try:
            from packages.graph_scale.answer_bridge import _store
            store = _store()
        except Exception:
            store = None
    if store is None:
        return []

    import numpy as np

    fa = _facts_fn(store)
    engine = LeapEngine(emb, facts_about=fa)
    rng = np.random.default_rng(seed if seed is not None else int(time.time()) % 100_000)

    # candidate sources: emb terms that actually carry SPECIFIC relational structure in the KG
    terms = engine._terms
    idxs = rng.permutation(len(terms))
    known = {(r.get("a"), r.get("b")) for r in HM._rows()}
    minted: list[dict[str, Any]] = []

    for i in idxs:
        if len(minted) >= max_mint:
            break
        source = terms[int(i)]
        edges = fa(source)
        if not _specific_relations(edges):
            continue                                   # only generic edges → nothing structural to carry
        target, tgt_edges = _pick_target(engine, source, edges)
        if not target:
            continue
        # Gentner systematicity: only carry relations the TARGET also participates in (shared structure).
        shared = {str(r) for (_s, r, _o) in tgt_edges} & _specific_relations(edges)
        if not shared:
            continue
        got = 0
        for c in engine.transfer(source, target, k_map=3, limit=8, only_relations=shared):
            if got >= per_source or len(minted) >= max_mint:
                break
            if not c.triple:
                continue
            tgt, rel, obj = c.triple
            if str(rel) in _GENERIC:
                continue                               # keep the ledger to structural leaps
            obj = str(obj)
            if not obj or obj == tgt or obj == source:
                continue
            pair = tuple(sorted((str(tgt), obj)))
            if pair in known:
                continue
            if HM._kg_edge_between(store, tgt, obj):
                continue                               # KG already holds it — not a discovery
            carried = c.derivation.get("carried_edge")
            row = {
                "a": pair[0], "b": pair[1], "relation": str(rel), "subject": str(tgt), "object": obj,
                "resonance": round(float(c.score), 4), "status": "unverified", "source": "leap",
                "question": f"Is it true that {tgt} {str(rel).replace('_', ' ')} {obj}?",
                "derivation": {"kind": "structure_transfer", "analogy": f"{source} → {target}",
                               "carried_edge": list(carried) if carried else None},
                "minted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            HM._append(row)
            known.add(pair)
            minted.append(row)
            got += 1
    return minted


def run_once(max_mint: int = 8, investigate: int = 3, seed: int | None = None) -> dict[str, Any]:
    """One full turn of the closed loop: mint leaps → push them as gated questions → settle any that
    external evidence has since confirmed. Safe to call from the autonomous daemon; asserts nothing."""
    from packages.graph_scale import hypothesis_minter as HM
    minted = mint_leaps(max_mint=max_mint, seed=seed)
    pushed = 0
    try:
        pushed = HM.investigate(limit=investigate)         # shared gate: leap questions enter the queue
    except Exception:
        pushed = 0
    try:
        settled = HM.settle()                              # shared gate: KG-confirmed leaps graduate
    except Exception:
        settled = {"confirmed": 0, "checked": 0}
    return {
        "minted": len(minted),
        "examples": [{"claim": f"{r['subject']} {r['relation']} {r['object']}",
                      "via": r["derivation"]["analogy"], "score": r["resonance"]} for r in minted[:5]],
        "pushed_to_evidence_queue": pushed,
        "settled": settled,
        "note": "Every minted row is a CONJECTURE (status=unverified); only external evidence through "
                "the existing consensus/judge/quarantine gates can confirm it. Nothing asserted.",
    }


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_once(seed=0), ensure_ascii=False, indent=2))
