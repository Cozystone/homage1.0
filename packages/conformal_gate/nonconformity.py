# -*- coding: utf-8 -*-
"""Nonconformity adapter — assemble ATANOR's EXISTING confidence signals into one scalar.

The conformal layer (``conformal.py``) makes the acceptance threshold rigorous REGARDLESS
of this scalar's scale or even its AUC. So this adapter's only job is to produce a score
that *ranks* answers by doubt (higher = less confident). A weak ranking is paid for in
abstention rate, never in safety — that is the whole point of NS-1.

Design rules (BINDING, honesty)
-------------------------------
* Only PRESENT signals contribute. A missing signal is never invented; the aggregate is
  the mean of whatever real doubt-contributions exist.
* If NO signal is present, nonconformity = 1.0 (max) -> the gate abstains. Absence of
  evidence is treated as doubt, never as confidence.
* Every ``from_*`` reader consumes a REAL object produced by a real ATANOR module. The
  imports are LAZY (inside the functions) so that importing this package pulls in no heavy
  dependency and no data directory.

Wiring status (see WIRING_STATUS below and the report):
  WIRED  cheaply-importable, pure, unit-tested against the real objects:
    - from_activated_subgraph  <- graph_scale.spreading_activation.spread() -> ActivatedSubgraph
    - from_epistemic_answer     <- reasoning_vm.epistemic_memory.EpistemicGraph.answer()
    - from_consensus            <- knowledge_acquisition.consensus.ConsensusResult
    - from_cleanup_sims         <- vsa_reasoning.fhrr_core.cleanup / RingCodebook.decode
    - from_referent_resonance   <- cgsr.cgsr.referent_resonance.resonance / select_resonant_facts
  WIRING-PENDING at production scale (needs the live 141M-edge store + live answer path):
    the shipped answer object (graph_native_answer.compose) returns a HARDCODED
    confidence=0.85 and DISCARDS the ActivatedSubgraph it computed. To make the gate live
    on real answers the answer path must attach the real signals — see WIRING_STATUS.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Optional

# Recognition ladder -> ordinal doubt in [0,1] (KNOWN < INHERITED < ... < GUESSED, per the
# research doc; INFERRED/UNKNOWN placed by their confidence semantics in epistemic_memory).
RUNG_DOUBT: dict[str, float] = {
    "KNOWN": 0.00,
    "INHERITED": 0.15,
    "INFERRED": 0.30,
    "SCHEMA": 0.45,
    "ANALOGIZED": 0.60,
    "GUESSED": 0.85,
    "UNKNOWN": 1.00,
}

WIRING_STATUS: dict[str, str] = {
    "from_activated_subgraph": "WIRED (graph_scale.spreading_activation.spread -> ActivatedSubgraph; "
                               "activation mass = sum(.activation), path count = len(.edges), "
                               "top delivered = max edge[3]). Pure given facts_about.",
    "from_epistemic_answer": "WIRED (reasoning_vm.epistemic_memory.EpistemicGraph.answer -> "
                             "{epistemic_type, confidence}). Pure; needs a populated graph for real data.",
    "from_consensus": "WIRED (knowledge_acquisition.consensus.ConsensusResult.n_domains/corroborated). "
                      "Pure in-memory tally; only meaningful when web sightings are fed.",
    "from_cleanup_sims": "WIRED (vsa_reasoning.fhrr_core.cleanup returns top-1 resonance; margin = "
                         "top1-top2 must be derived from the sims array). numpy only.",
    "from_referent_resonance": "WIRED (cgsr.cgsr.referent_resonance.resonance in [0,1]; "
                               "select_resonant_facts kept-ratio). Pure stdlib.",
    "PRODUCTION_ANSWER_PATH": "WIRING-PENDING. graph_scale/graph_native_answer.py:226 sets "
                              "confidence=0.85 (constant) and graph_scale/graph_native_answer.py:153 "
                              "computes `sg` then discards it. To go live: (1) attach the real "
                              "ActivatedSubgraph to the returned dict; (2) route through EpistemicGraph "
                              "for epistemic_type+confidence; (3) feed ConsensusTally on web corroboration; "
                              "(4) call SignalVector + gate before returning in "
                              "graph_scale/answer_bridge.py:answer_from_triples (~line 740). "
                              "Requires the live TripleStore (data/graph_scale/kg_triples, ~2GB).",
}


@dataclass
class SignalVector:
    """A candidate answer's real confidence signals. All optional: only present signals count."""
    activation_mass: Optional[float] = None      # sum of ActivatedSubgraph.activation
    support_path_count: Optional[int] = None      # len(ActivatedSubgraph.edges)
    top_delivered: Optional[float] = None         # max delivered activation over edges (margin proxy)
    epistemic_rung: Optional[str] = None          # KNOWN/INHERITED/INFERRED/SCHEMA/ANALOGIZED/GUESSED/UNKNOWN
    graded_confidence: Optional[float] = None     # EpistemicGraph confidence in [0,1]
    consensus_domains: Optional[int] = None       # ConsensusResult.n_domains
    corroborated: Optional[bool] = None           # ConsensusResult.corroborated
    cleanup_resonance: Optional[float] = None     # VSA/FHRR top-1 resonance in [-1,1]
    cleanup_margin: Optional[float] = None         # top1 - top2 similarity (>=0)
    referent_resonance: Optional[float] = None    # referent type-match resonance in [0,1]
    felt_score: Optional[float] = None            # subjective felt_score in [0,1]
    semantic_entropy: Optional[float] = None      # NS-2: normalized disagreement of K diverse graph traversals, [0,1]
    subject_coverage: Optional[float] = None      # base_brain define lane: fraction of the query's subject content-tokens the answer covers, [0,1] (1=full referent match, low=wrong-referent/partial define)

    def merge(self, other: "SignalVector") -> "SignalVector":
        """Overlay non-None fields of ``other`` onto a copy of ``self``."""
        out = SignalVector(**{f.name: getattr(self, f.name) for f in fields(self)})
        for f in fields(other):
            v = getattr(other, f.name)
            if v is not None:
                setattr(out, f.name, v)
        return out

    def present(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}


# --------------------------------------------------------------------------------------
# Per-signal doubt maps -> [0,1], higher = less confident. (Only shape matters; conformal
# calibrates the threshold. These are monotone, bounded, and never fabricate.)
# --------------------------------------------------------------------------------------
def _sat_low(x: float, scale: float) -> float:
    """Map a non-negative 'more is better' quantity to doubt in (0,1]: 1/(1+x/scale)."""
    x = max(0.0, float(x))
    return 1.0 / (1.0 + x / scale)


def _doubt_contributions(sv: SignalVector) -> dict[str, float]:
    d: dict[str, float] = {}
    if sv.epistemic_rung is not None:
        d["rung"] = RUNG_DOUBT.get(str(sv.epistemic_rung).upper(), 1.0)
    if sv.graded_confidence is not None:
        d["graded_confidence"] = 1.0 - _clip01(sv.graded_confidence)
    if sv.activation_mass is not None:
        d["activation_mass"] = _sat_low(sv.activation_mass, scale=2.0)
    if sv.support_path_count is not None:
        d["support_paths"] = _sat_low(sv.support_path_count, scale=3.0)
    if sv.top_delivered is not None:
        d["top_delivered"] = _sat_low(sv.top_delivered, scale=0.5)
    if sv.consensus_domains is not None:
        # 0 domains -> 1.0 doubt; each independent domain sharply reduces it.
        d["consensus"] = _sat_low(sv.consensus_domains, scale=1.0)
    elif sv.corroborated is not None:
        d["consensus"] = 0.2 if sv.corroborated else 0.9
    if sv.cleanup_resonance is not None:
        # resonance in [-1,1] -> doubt in [0,1]: +1 -> 0 doubt, -1 -> 1 doubt.
        d["cleanup_resonance"] = (1.0 - _clip_pm1(sv.cleanup_resonance)) / 2.0
    if sv.cleanup_margin is not None:
        d["cleanup_margin"] = _sat_low(sv.cleanup_margin, scale=0.25)
    if sv.referent_resonance is not None:
        d["referent_resonance"] = 1.0 - _clip01(sv.referent_resonance)
    if sv.felt_score is not None:
        d["felt"] = 1.0 - _clip01(sv.felt_score)
    if sv.semantic_entropy is not None:
        # NS-2: entropy already in [0,1] and already oriented (high = disagreement = doubt).
        d["semantic_entropy"] = _clip01(sv.semantic_entropy)
    if sv.subject_coverage is not None:
        # define lane: a confident define whose answer leaves the query's subject content-tokens
        # UNCOVERED is a wrong-referent match ('black hole' -> 'Black is a color'; 'gold rush' ->
        # 'Gold is an album'). coverage in [0,1] (1=full) -> doubt = 1 - coverage. The near-constant
        # graded_confidence cannot see this; the coverage doubt is what separates a good define
        # (photosynthesis, coverage 1.0) from a wrong-referent define (coverage <= 0.5).
        d["subject_coverage"] = 1.0 - _clip01(sv.subject_coverage)
    return d


def nonconformity(sv: SignalVector, weights: Optional[dict[str, float]] = None) -> float:
    """Combine the PRESENT signals into a scalar nonconformity in [0,1] (higher = doubt).

    Aggregation = weighted mean over present doubt-contributions. No present signal ->
    returns 1.0 (abstain). ``weights`` may up/down-weight named contributions
    (keys of ``_doubt_contributions``); unlisted present signals default to weight 1.
    """
    d = _doubt_contributions(sv)
    if not d:
        return 1.0
    if weights is None:
        return float(sum(d.values()) / len(d))
    num = 0.0
    den = 0.0
    for k, v in d.items():
        w = float(weights.get(k, 1.0))
        num += w * v
        den += w
    return float(num / den) if den > 0 else 1.0


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else float(x))


def _clip_pm1(x: float) -> float:
    return -1.0 if x < -1 else (1.0 if x > 1 else float(x))


# --------------------------------------------------------------------------------------
# Readers of REAL ATANOR signal objects (lazy imports; each maps one source -> partial SV)
# --------------------------------------------------------------------------------------
def from_activated_subgraph(sg: Any) -> SignalVector:
    """Read a real ``graph_scale.spreading_activation.ActivatedSubgraph``.

    activation mass = sum of activations (excluding the anchor's seed 1.0),
    support path count = number of reasoning edges,
    top delivered = the strongest single delivered activation (a margin proxy).
    """
    activation = dict(getattr(sg, "activation", {}) or {})
    anchor = getattr(sg, "anchor", None)
    mass = sum(v for k, v in activation.items() if k != anchor)
    edges = list(getattr(sg, "edges", []) or [])
    top = max((e[3] for e in edges if len(e) > 3), default=0.0)
    return SignalVector(activation_mass=float(mass),
                        support_path_count=int(len(edges)),
                        top_delivered=float(top))


def from_epistemic_answer(res: dict) -> SignalVector:
    """Read a real ``EpistemicGraph.answer()`` result dict {epistemic_type, confidence, ...}."""
    return SignalVector(epistemic_rung=res.get("epistemic_type"),
                        graded_confidence=(None if res.get("confidence") is None
                                           else float(res["confidence"])))


def from_consensus(result: Any) -> SignalVector:
    """Read a real ``knowledge_acquisition.consensus.ConsensusResult`` (or None = no consensus)."""
    if result is None:
        return SignalVector(consensus_domains=0, corroborated=False)
    return SignalVector(consensus_domains=int(getattr(result, "n_domains", 0)),
                        corroborated=bool(getattr(result, "corroborated", False)))


def from_cleanup_sims(sims: Any) -> SignalVector:
    """Read a VSA/FHRR cleanup similarity array (the `sims` computed inside
    ``vsa_reasoning.fhrr_core.cleanup``). Resonance = top-1; margin = top1 - top2."""
    import numpy as np
    a = np.sort(np.asarray(sims, dtype=float).ravel())[::-1]
    if a.size == 0:
        return SignalVector()
    top1 = float(a[0])
    top2 = float(a[1]) if a.size > 1 else -1.0
    return SignalVector(cleanup_resonance=top1, cleanup_margin=max(0.0, top1 - top2))


def from_referent_resonance(value: float) -> SignalVector:
    """Read a real ``cgsr.cgsr.referent_resonance.resonance`` scalar in [0,1]
    (or a kept-fact ratio from ``select_resonant_facts``)."""
    return SignalVector(referent_resonance=float(value))


def from_felt(felt_result: dict) -> SignalVector:
    """Read a real ``subjective.felt_judgment.felt_judgment`` result: the chosen option's
    felt_score. NOTE (honesty): felt ranks a SET of options, it is not a single-answer
    correctness score — used here only as a weak auxiliary doubt signal."""
    chosen_id = felt_result.get("chosen")
    ranked = felt_result.get("ranked") or []
    score = None
    for r in ranked:
        if r.get("id") == chosen_id:
            score = r.get("felt_score")
            break
    if score is None and ranked:
        score = ranked[0].get("felt_score")
    return SignalVector(felt_score=(None if score is None else float(score)))


def from_semantic_entropy(entropy: Any) -> SignalVector:
    """NS-2 reader. Accepts either a bare float in [0,1] (the normalized cluster entropy of
    K diverse graph traversals) or a ``semantic_entropy.EntropyResult``. Higher entropy =
    the traversals disagree on the answer = higher nonconformity.

    Abstain semantics: a result whose modal answer is None (the traversals reached NO answer
    at all — not merely disagreed) is treated as maximum doubt (entropy 1.0), never as the
    'unanimous -> 0' that a raw entropy would report for a degenerate all-None tally."""
    if entropy is None:
        return SignalVector()                                  # signal failed to compute -> absent -> abstain
    modal = getattr(entropy, "modal_answer", "__present__")
    val = getattr(entropy, "entropy", entropy)
    if modal is None:                                          # reached nothing anywhere -> max doubt
        return SignalVector(semantic_entropy=1.0)
    return SignalVector(semantic_entropy=_clip01(float(val)))


def from_resonance_margin(result: Any) -> SignalVector:
    """NS-5 reader. Consumes a ``resonance_verifier.verify_binding`` result dict
    ``{accepted, resonance, margin, ...}`` and maps it onto the (M1-calibrated) VSA doubt
    fields: top-1 ``cleanup_resonance`` (convergence) and ``cleanup_margin`` (top1-top2
    separation). A failure-to-converge is reported as its (low) resonance + (tiny) margin, so
    nonconformity is HIGH -> abstain; never dropped to 'absent-but-confident'.

    A result that could not be produced at all (None) -> empty SignalVector (absent signal;
    if it is the only signal the gate abstains -- absence of evidence = doubt)."""
    if not result or result.get("resonance") is None:
        return SignalVector()
    return SignalVector(cleanup_resonance=float(result["resonance"]),
                        cleanup_margin=float(result.get("margin", 0.0)))
