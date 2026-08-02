# -*- coding: utf-8 -*-
"""Temporal-anomaly judgment from the LEARNED precedence field (no hand-ranked lexicon).

A paradox is judged, not looked up: on one subject, two timestamped events whose timestamps say
t(a) < t(b) while the learned field says a canonically happens AFTER b with high confidence, is
physically impossible. A predicate whose tokens the field has never seen yields NO judgment
(fail-closed honesty), never a guess. See docs/ATANOR_temporal_causal_physics.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from packages.temporal_reasoning.precedence_field import PrecedenceField

_TS_TZ = re.compile(r"\s*(UTC|GMT|Z)$")


def parse_ts(o: str) -> datetime | None:
    s = _TS_TZ.sub("", str(o).strip())
    try:
        return datetime.fromisoformat(s)      # ISO 8601 = spec grammar, not world knowledge
    except (ValueError, AttributeError):
        return None


@dataclass
class Paradox:
    subject: str
    early_pred: str          # the predicate whose timestamp is EARLIER
    early_ts: str
    late_pred: str           # the predicate whose timestamp is LATER
    late_ts: str
    early_bone: str
    late_bone: str
    confidence: float        # learned P(late_pred canonically precedes early_pred)

    @property
    def flagged_slot(self) -> str:
        # the canonically-later event that happened impossibly early is the offender
        return f"{self.subject}.{self.early_pred}"

    def sentence(self) -> str:
        return (f"Physically impossible sequence for {self.subject}: {self.early_pred} "
                f"({self.early_ts}, {self.early_bone}) is recorded BEFORE {self.late_pred} "
                f"({self.late_ts}, {self.late_bone}), but {self.late_pred.replace('_', ' ')} "
                f"canonically precedes {self.early_pred.replace('_', ' ')} "
                f"(learned confidence {self.confidence:.2f}).")


_STORE_CACHE: list = []          # [store_or_None] once loaded; empty = not yet attempted


def _cached_store():
    if not _STORE_CACHE:
        from packages.temporal_reasoning.precedence_field import EvidenceStore
        _STORE_CACHE.append(EvidenceStore.load())
    return _STORE_CACHE[0]


_WEB_CACHE: list = []            # [counts] once loaded


def _web_verdict(pred_a: str, pred_b: str, min_domains: int = 2) -> float | None:
    """P(pred_a precedes pred_b) from cross-domain web consensus, or None if too few sources.
    This tier sits ABOVE the global phase field: a pair confirmed by >=2 independent domains is
    trusted over polysemy-polluted global co-occurrence (fixes 'ignition<launch' drowned by wiki)."""
    from packages.temporal_reasoning.web_explorer import web_consensus
    if not _WEB_CACHE:
        from packages.temporal_reasoning.web_explorer import load_web_counts
        _WEB_CACHE.append(load_web_counts())
    v = web_consensus(pred_a, pred_b, _WEB_CACHE[0])
    if v is None or (v[1] + v[2]) < min_domains:
        return None
    return v[0]


def _ctx_tokens(subject: str, pred_a: str, pred_b: str) -> list[str]:
    toks = set()
    for src in (subject, pred_a, pred_b):
        toks.update(t for t in re.split(r"[^a-zA-Z]+", src.lower()) if len(t) >= 3)
    return sorted(toks)


def counterfactual(bones: dict, edits: dict, field: PrecedenceField | None,
                   store=None) -> dict:
    """Counterfactual query on the learned causal-order world model (Gemini pillar 2): 'if these
    events had happened at these OTHER times, would the physical impossibilities change?'
    `edits` maps a bone id -> a replacement object (usually a new timestamp). Returns the paradoxes
    in the factual world, the counterfactual world, and the delta (which impossibilities the edit
    would REMOVE and which it would INTRODUCE). No hardcoded causality -- the verdict comes entirely
    from the learned precedence field, so this reasons, it does not look up."""
    cf_bones = dict(bones)
    for bid, new_o in edits.items():
        if bid in cf_bones:
            s, p, _ = cf_bones[bid]
            cf_bones[bid] = (s, p, new_o)
    fact = {px.flagged_slot: px for px in detect_paradoxes(bones, field, store=store)}
    cf = {px.flagged_slot: px for px in detect_paradoxes(cf_bones, field, store=store)}
    removed = sorted(set(fact) - set(cf))
    introduced = sorted(set(cf) - set(fact))
    return {"factual_paradoxes": sorted(fact), "counterfactual_paradoxes": sorted(cf),
            "removed_by_edit": removed, "introduced_by_edit": introduced,
            "resolves": bool(removed) and not introduced}


def detect_paradoxes(bones: dict, field: PrecedenceField | None,
                     threshold: float = 0.97, store=None) -> list[Paradox]:
    """bones: {bid: (s, p, o)}. HIERARCHICAL learned judgment, all thresholds holdout-calibrated
    (never exam-tuned), one paradox per offending slot:
      Tier 1 -- sense-verified: context-conditioned pair observations (sentences sharing a context
                word with this subject/predicates). Strongest: 'restored castles' cannot vouch
                against 'telemetry restored'. Claim >=0.9 posterior; a contrary ctx verdict VETOES.
      Tier 2 -- direct pair observations (>=5 obs, posterior >=0.9).
      Tier 2.5 -- web k-source consensus (>=2 independent domains from live roaming): OUTRANKS the
                global phase, because domain-diverse agreement beats polysemy-polluted co-occurrence.
      Tier 3 -- global phase coordinate at the calibrated 0.97 bar (precision 0.923 on holdout);
                only when no ctx/pair/web evidence decides.
    Unknown vocabulary or absent field -> no judgment (honest), never a guess."""
    if field is None:
        return []
    from packages.temporal_reasoning.precedence_field import posterior_direction
    if store is None:
        store = _cached_store()
    per_subj: dict[str, list] = {}
    for bid, (s, p, o) in bones.items():
        ts = parse_ts(o)
        if ts is not None:
            per_subj.setdefault(s, []).append((p, o, ts, bid))
    best: dict[str, Paradox] = {}                        # flagged_slot -> strongest paradox
    for s, evs in per_subj.items():
        for i, (p_a, o_a, t_a, b_a) in enumerate(evs):
            for p_b, o_b, t_b, b_b in evs[i + 1:]:
                if t_a == t_b:
                    continue
                (pe, oe, te, be), (pl, ol, tl, bl) = sorted(
                    [(p_a, o_a, t_a, b_a), (p_b, o_b, t_b, b_b)], key=lambda x: x[2])
                # judge: does pl canonically precede pe? (if yes, pe-being-stamped-earlier is a paradox)
                conf = None
                if store is not None:
                    n_ab, n_ba = store.ctx_evidence(pl, pe, _ctx_tokens(s, pl, pe))
                    if n_ab + n_ba >= 3:                 # Tier 1: sense-verified
                        post = posterior_direction(n_ab, n_ba)
                        conf = post if post >= 0.9 else (0.0 if post <= 0.5 else None)  # veto on contrary
                    if conf is None:
                        n_ab, n_ba = store.pair_evidence(pl, pe)
                        if n_ab + n_ba >= 5:             # Tier 2: direct pair
                            post = posterior_direction(n_ab, n_ba)
                            conf = post if post >= 0.9 else (0.0 if post <= 0.5 else None)
                if conf is None:                         # Tier 2.5: web k-source consensus --
                    wc = _web_verdict(pl, pe)            # domain-diverse, OUTRANKS polysemy-polluted
                    if wc is not None:                   # global stats (the ignition<launch fix)
                        conf = wc if wc >= 0.9 else (0.0 if wc <= 0.5 else None)
                if conf is None:                         # Tier 3: global phase, calibrated bar
                    g = field.order_confidence(pl, pe)
                    conf = g if (g is not None and g >= threshold) else 0.0
                if conf and conf >= 0.9:
                    px = Paradox(s, pe, oe, pl, ol, be, bl, conf)
                    old = best.get(px.flagged_slot)
                    if old is None or px.confidence > old.confidence:
                        best[px.flagged_slot] = px       # one report per offending slot
    return list(best.values())
