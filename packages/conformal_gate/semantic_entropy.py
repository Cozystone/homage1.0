# -*- coding: utf-8 -*-
"""NS-2 — graph-native semantic entropy (a nonconformity signal for the conformal gate).

Semantic entropy (Kuhn, Gal, Farquhar 2023) samples K generations, clusters them by MEANING,
and takes the entropy of the cluster distribution: high entropy = the samples disagree about
the answer = the model is uncertain / likely wrong. Their clustering uses an NLI model.

ATANOR is No-LLM and graph-native, so the two moving parts are replaced by graph machinery:

  * "K samples"  -> K DIVERSE spreading-activation traversals of the SAME query. Diversity is
    injected honestly: stochastic edge dropout (bootstrap-resample the anchor's evidence so
    different support paths survive each run) + small decay/threshold jitter. Genuinely
    different paths, not cosmetic noise. Each traversal returns ONE answer entity: the
    highest-activation node among the candidate answer values (or the top lit-up concept).

  * "cluster by meaning (NLI)"  -> cluster by NODE IDENTITY. Two traversals agree iff they
    returned the same node id (optionally merged through a caller-supplied ``sameAs`` /
    equivalence map). Identity clustering is the graph-native replacement for NLI: in a KG the
    answer IS a node, and node equality is the ground-truth semantic-equivalence relation, so
    no learned entailment model is needed.

Then entropy over the cluster-mass distribution, normalized to [0,1] by ``log(K)`` so it drops
straight into ``nonconformity.SignalVector.semantic_entropy`` (higher = more doubt). Unanimous
traversals -> 0 (accept-cheap); a K-way split -> 1 (abstain).

Honest boundary (measured, see the M3 probe): this signal detects AMBIGUITY-driven error
(competing multi-hop paths). It is BLIND to a graph that is confidently, unanimously WRONG
(a corrupt/stale fact): every traversal agrees on the wrong node -> entropy 0. That failure
mode needs a different signal (epistemic override-risk / consensus), not this one.

Pure numpy + stdlib. Imports ``graph_scale.spreading_activation.spread`` READ-ONLY.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

FactsAbout = Callable[[str], "list[tuple[str, str, str]]"]


@dataclass
class EntropyResult:
    entropy: float                       # normalized cluster entropy in [0,1] (0 = unanimous)
    raw_entropy_nats: float              # unnormalized Shannon entropy (nats)
    modal_answer: Optional[str]          # the plurality answer entity (None = reached nothing)
    modal_fraction: float                # mass of the modal cluster in [0,1]
    n_clusters: int                      # number of distinct answer clusters (incl. a None cluster)
    n_effective: float                   # exp(raw_entropy) — effective number of answers
    cluster_mass: dict                   # {canonical_answer: fraction}
    answers: list                        # per-traversal raw answer entity (pre-canonicalization)
    K: int


def _dropout_facts(facts_about: FactsAbout, rng, p_drop: float) -> FactsAbout:
    """Wrap ``facts_about`` so each returned row survives with prob ``1 - p_drop`` (per call).

    This is a bootstrap resample of the evidence: dropping a support edge removes one path, so
    a close race between two answer hubs resolves differently across traversals while a
    lopsided one stays put. ``spread`` visits each node once, so a node's rows are filtered
    exactly once per traversal -> the traversal is internally consistent, only the ensemble
    varies. p_drop<=0 is a no-op (deterministic traversal)."""
    if p_drop <= 0.0:
        return facts_about

    def wrapped(term: str):
        rows = facts_about(term) or []
        return [r for r in rows if rng.random() >= p_drop]

    return wrapped


def _answer_of(sg: Any, answer_values: Optional[frozenset]) -> Optional[str]:
    """The single answer entity a traversal 'returned'.

    If ``answer_values`` is given, it is the highest-activation node WITHIN that candidate set
    (the query's answer slot). Otherwise it is the top lit-up concept (excluding the anchor).
    None if nothing qualifying was reached."""
    activation = getattr(sg, "activation", {}) or {}
    anchor = getattr(sg, "anchor", None)
    if answer_values is not None:
        best, best_a = None, 0.0
        for node, a in activation.items():
            if node in answer_values and a > best_a:
                best, best_a = node, a
        return best
    tops = sg.top_concepts(k=1) if hasattr(sg, "top_concepts") else []
    return tops[0][0] if tops else None


def semantic_entropy_full(
    anchor: str,
    facts_about: FactsAbout,
    *,
    answer_values: Optional[Sequence[str]] = None,
    intent_preds: tuple[str, ...] = (),
    K: int = 8,
    seed: int = 0,
    p_drop: float = 0.25,
    decay_jitter: float = 0.06,
    threshold_jitter: float = 0.02,
    equivalence: Optional[dict] = None,
    spread_kwargs: Optional[dict] = None,
) -> EntropyResult:
    """Run K diverse traversals from ``anchor`` and return the full entropy breakdown.

    ``facts_about`` : term -> stored triples (the exact interface ``spread`` consumes).
    ``answer_values``: candidate answer node ids (the query's answer slot). If None, the top
                       lit-up concept is used as the traversal's answer.
    ``equivalence``  : optional {node: canonical} sameAs/equivalence map for identity clustering.
    """
    import numpy as np
    from packages.graph_scale.spreading_activation import spread, _DECAY, _THRESHOLD

    rng = np.random.default_rng(seed)
    cand = frozenset(str(v) for v in answer_values) if answer_values is not None else None
    equ = equivalence or {}
    base_kw = dict(spread_kwargs or {})

    raw_answers: list[Optional[str]] = []
    for _ in range(int(K)):
        fa = _dropout_facts(facts_about, rng, p_drop)
        decay = float(np.clip(_DECAY + rng.normal(0.0, decay_jitter), 0.30, 0.90))
        thr = float(np.clip(_THRESHOLD + rng.normal(0.0, threshold_jitter), 0.02, 0.30))
        kw = dict(base_kw)
        kw.setdefault("intent_preds", intent_preds)
        kw["decay"] = decay
        kw["threshold"] = thr
        sg = spread(anchor, fa, **kw)
        raw_answers.append(_answer_of(sg, cand))

    # ---- identity clustering (+ sameAs) -------------------------------------------------
    def canon(a: Optional[str]) -> Optional[str]:
        if a is None:
            return None
        return equ.get(a, a)

    mass: dict = {}
    for a in raw_answers:
        c = canon(a)
        mass[c] = mass.get(c, 0) + 1
    total = sum(mass.values()) or 1
    frac = {k: v / total for k, v in mass.items()}

    raw_H = -sum(p * math.log(p) for p in frac.values() if p > 0.0)
    # Normalized entropy (Shannon EFFICIENCY): divide by log of the number of DISTINCT clusters
    # actually observed, NOT by log(K). Normalizing by log(K) assumes up to K distinct answers
    # and crushes a decisive 2-way 50/50 split to log(2)/log(K) (~0.2 at K=24) -- fine for a
    # rank-only AUC (K is fixed) but it starves entropy's share of the weighted-mean aggregate.
    # Efficiency puts "no clear winner among the options that appeared" at ~1.0, so the signal
    # occupies [0,1] like the others and contributes fairly. A unanimous single cluster -> 0.
    n_obs = len(frac)
    norm = raw_H / math.log(n_obs) if n_obs > 1 else 0.0
    norm = 0.0 if norm < 0.0 else (1.0 if norm > 1.0 else norm)

    modal_answer, modal_fraction = None, 0.0
    for k, v in frac.items():
        if v > modal_fraction:
            modal_answer, modal_fraction = k, v

    return EntropyResult(
        entropy=float(norm),
        raw_entropy_nats=float(raw_H),
        modal_answer=modal_answer,
        modal_fraction=float(modal_fraction),
        n_clusters=len(frac),
        n_effective=float(math.exp(raw_H)),
        cluster_mass=frac,
        answers=raw_answers,
        K=int(K),
    )


def semantic_entropy(
    anchor: str,
    facts_about: FactsAbout,
    *,
    answer_values: Optional[Sequence[str]] = None,
    K: int = 8,
    **kwargs: Any,
) -> float:
    """Convenience scalar: the normalized cluster entropy in [0,1] (higher = disagreement).

    Signature matches the task's ``semantic_entropy(query, graph, K)`` shape: ``anchor`` is the
    query node, ``facts_about`` is the graph accessor, ``K`` is the traversal count."""
    return semantic_entropy_full(anchor, facts_about, answer_values=answer_values,
                                 K=K, **kwargs).entropy
