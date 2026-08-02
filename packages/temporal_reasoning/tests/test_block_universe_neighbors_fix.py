# -*- coding: utf-8 -*-
"""Sealed gates for the block-universe temporal-bidder FIRE fix (2026-07-23).

The measured problem (V2.1 landing): the temporal bidder fired ~0% because
  1. `_neighbors` selected the phase-NEAREST token, whose order_confidence = sigmoid(≈0) ≈ 0.5 BY
     CONSTRUCTION on a dense 114k-token field, so every surfaced "next" step was low-confidence AND
     semantic noise -> correctly rejected by the 0.6 gate -> nothing ever fired; and
  2. the field's top-seen tokens were register-pollution markup (quot/ref/amp/article/page/user).

The fix (packages/temporal_reasoning): `_neighbors` now surfaces only candidates that clear a
confidence MARGIN in the right direction (fail-closed), markup is filtered, and — on the clean causal
field — the mined DIRECTED pair counts (typed causal edges) rank the successor so the walk is the
learned successor, not the phase-nearest. These gates are deterministic on hand-built fixtures.
"""
from __future__ import annotations

from collections import Counter

import pytest

from packages.temporal_reasoning.block_universe import BlockUniverse, _ORDER_MARGIN
from packages.temporal_reasoning.precedence_field import PrecedenceField, MARKUP_STOP
from packages.temporal_reasoning.unified_timeline import Timeline


# ── GATE (a): _neighbors clears a confidence MARGIN, never the phase-nearest ~0.5 token ──────────────

def _cluster_field() -> PrecedenceField:
    """A dense near-anchor cluster (phase-nearest -> order_conf ~0.5 by construction) plus one real
    event a meaningful phase gap ahead and one behind. This is the exact failure shape the production
    field had: the nearest token is 0.5-ordered noise."""
    return PrecedenceField(
        phase={"anchor": 0.0, "noisea": 0.002, "noiseb": 0.004, "noisec": -0.003,
               "realnext": 0.85, "realprev": -0.85},
        seen={t: 5 for t in ("anchor", "noisea", "noiseb", "noisec", "realnext", "realprev")})


def test_gate_a_neighbors_clears_margin_not_phase_nearest():
    bu = BlockUniverse(Timeline(), _cluster_field())
    fwd = bu._neighbors("anchor", ahead=True, k=5, exclude={"anchor"})
    assert fwd, "a confident next-event exists past the margin"
    surfaced = [t for t, _ in fwd]

    # the phase-NEAREST tokens (gap ~0.002 -> order_conf ~0.5) are NEVER surfaced
    assert not ({"noisea", "noiseb", "noisec"} & set(surfaced)), surfaced
    # the surfaced next-event is the real one past the margin
    assert surfaced[0] == "realnext"

    # ASSERT THE CONFIDENCE: the surfaced step clears the 0.6 threshold with real signal (not ~0.5)
    conf = bu.field.order_confidence("anchor", "realnext")
    assert conf is not None and conf >= _ORDER_MARGIN, conf
    assert conf == pytest.approx(0.701, abs=0.01)

    # and the near-0.5 token, had it been selected (the OLD behavior), would have been ~0.5 -> rejected
    assert bu.field.order_confidence("anchor", "noiseb") == pytest.approx(0.5, abs=0.01)

    # backward is symmetric: the confident PRIOR event, not the nearest noise
    bwd = [t for t, _ in bu._neighbors("anchor", ahead=False, k=5, exclude={"anchor"})]
    assert bwd[:1] == ["realprev"] and not ({"noisea", "noiseb", "noisec"} & set(bwd))


def test_gate_a_fail_closed_when_nothing_clears_the_margin():
    # a field where every ahead token sits INSIDE the margin -> no confident next -> empty (abstain)
    f = PrecedenceField(phase={"anchor": 0.0, "a": 0.05, "b": 0.1, "c": 0.2},
                        seen={t: 5 for t in ("anchor", "a", "b", "c")})
    bu = BlockUniverse(Timeline(), f)
    assert bu._neighbors("anchor", ahead=True, k=5, exclude={"anchor"}) == []   # fail-closed


# ── GATE (b): register-pollution markup is never surfaced as an event ────────────────────────────────

_POLLUTION = {"quot", "ref", "amp", "page", "article", "user", "http", "href", "wikipedia", "svg"}


def _polluted_field() -> PrecedenceField:
    """Markup tokens sit at gaps that WOULD clear the margin (and would be phase-nearest ahead), plus
    the real events. Without filtering, the walk would surface `quot`/`page`/`ref` as 'next events'."""
    return PrecedenceField(
        phase={"anchor": 0.0, "quot": 0.5, "ref": 0.6, "amp": 0.7, "page": 0.55,
               "realevent": 0.9, "user": -0.6, "priorevt": -0.9},
        seen={t: 1000 for t in ("anchor", "quot", "ref", "amp", "page",
                                "realevent", "user", "priorevt")})


def test_gate_b_markup_stoplist_covers_the_measured_polluters():
    # the tokens the V2.1 landing measured as dominating the field are all in the closed markup list
    for tok in ("quot", "ref", "amp", "article", "page", "user"):
        assert tok in MARKUP_STOP


def test_gate_b_register_pollution_never_surfaced_as_events():
    bu = BlockUniverse(Timeline(), _polluted_field())

    fwd = [t for t, _ in bu._neighbors("anchor", ahead=True, k=20, exclude={"anchor"})]
    assert "realevent" in fwd                       # the real event surfaces
    assert not (_POLLUTION & set(fwd)), fwd         # NONE of the markup does, though it clears the gap

    bwd = [t for t, _ in bu._neighbors("anchor", ahead=False, k=20, exclude={"anchor"})]
    assert "priorevt" in bwd and not (_POLLUTION & set(bwd)), bwd

    # and through the FULL surfacing paths (project_forward / infer_backward), never a markup token
    tl = Timeline(); tl.record("fact", "the anchor happened")
    bu2 = BlockUniverse(tl, _polluted_field())
    proj = bu2.project_forward(horizon=3)
    assert proj and all(p["event_token"] not in _POLLUTION for p in proj)
    assert all(p["hypothesis"] is True for p in proj)     # still hypothesis-tagged

    back = bu2.infer_backward("realevent", k=5)
    assert all(b["event_token"] not in _POLLUTION for b in back)
    assert all(b["hypothesis"] is True for b in back)


# ── GATE (c): the payoff — on a clean learned causal order the temporal path FIRES, meaningfully ─────

def _causal_fixture_field() -> PrecedenceField:
    """A clean learned causal order fit from REAL CAMEO-style directed pairs (the shape of the
    GDELT/postmortem causal corpus), with the typed causal edges carried as directed pair evidence.
    consult -> diplomacy (149) is the top observed successor; a phase-only walk would instead pick the
    never-observed phase-nearest token, so this fixture proves the typed-edge dominance."""
    pairs = {
        ("consult", "diplomacy"): 149, ("consult", "statement"): 84, ("consult", "intent"): 60,
        ("consult", "cooperate"): 53, ("diplomacy", "cooperate"): 40, ("diplomacy", "intent"): 40,
        ("cooperate", "aid"): 27, ("aid", "statement"): 6, ("intent", "aid"): 4,
        ("appeal", "consult"): 114, ("appeal", "diplomacy"): 31, ("assault", "consult"): 52,
        ("investigate", "statement"): 46, ("statement", "yield"): 73, ("demand", "diplomacy"): 18,
    }
    field = PrecedenceField.fit(Counter(pairs), min_count=1)
    field.event_vocab = set(field.phase)
    field.causal_pairs = dict(pairs)
    return field


def test_gate_c_walk_is_the_learned_successor_not_the_phase_nearest():
    """MEANINGFUL fire: from `consult`, the walk surfaces `diplomacy` (the observed top successor,
    count 149) — NOT the phase-nearest token, which for this fit is `investigate` (never observed as a
    consult-successor: pair count 0). Typed causal edges dominate the 1-D phase."""
    cf = _causal_fixture_field()
    bu = BlockUniverse(Timeline(), cf)
    nb = bu._neighbors("consult", ahead=True, k=5, exclude={"consult"})
    assert nb, "the clean causal field grounds a confident successor"
    assert nb[0][0] == "diplomacy", [t for t, _ in nb]          # the LEARNED successor, evidence-ranked

    # the phase-nearest ahead token is NOT diplomacy — proving the rerank did real work
    phase_nearest = min((t for t in cf.phase if cf.phase[t] > cf.phase["consult"] and t != "consult"),
                        key=lambda t: cf.phase[t] - cf.phase["consult"])
    assert phase_nearest != "diplomacy"
    assert cf.causal_pairs.get(("consult", phase_nearest), 0) == 0    # phase-nearest was never observed


def test_gate_c_temporal_path_fires_with_meaningful_confidence_and_is_hypothesis_tagged():
    cf = _causal_fixture_field()
    tl = Timeline(); tl.record("utterance", "what happens after nations consult?", who="user")
    proj = BlockUniverse(tl, cf).project_forward(horizon=3)

    assert proj, "the temporal path FIRES on a clean causal query (was ~0%)"
    assert proj[0]["event_token"] == "diplomacy"
    # every surfaced step clears the 0.6 threshold with REAL signal, and stays hypothesis-tagged
    assert all(p["confidence"] is not None and p["confidence"] >= _ORDER_MARGIN for p in proj), proj
    assert all(p["hypothesis"] is True for p in proj)
    # it is a genuine multi-step walk of the learned order (consult -> diplomacy -> ...)
    assert len(proj) >= 2 and proj[1]["after"] == "diplomacy"


def test_gate_c_genuinely_unknown_query_still_abstains_fail_closed():
    cf = _causal_fixture_field()
    tl = Timeline(); tl.record("utterance", "what happens after the zzzznonsense event?", who="user")
    assert BlockUniverse(tl, cf).project_forward(horizon=3) == []       # no known anchor -> abstain
    # a known-but-terminal anchor (nothing observed after it) also abstains, never invents
    assert BlockUniverse(Timeline(), cf).infer_backward("zzzznonsense") == []


# ── GATE (c) end-to-end: the FIRE-RATE through the real workspace bidder (imported, not modified) ─────

def _bidder():
    import packages.cgsr.cgsr.response_workspace as rw
    from packages.cgsr.cgsr.comprehension import perceive
    return rw, perceive


def test_gate_c_fire_rate_through_the_live_bidder_is_nonzero(monkeypatch):
    """Drive the ACTUAL bidder (response_workspace._temporal_candidate, unmodified) over the fixture
    field via its documented seam. Fire-rate on clean causal queries must be > 0% (the payoff), and
    genuinely-unknown queries must still abstain (fail-closed preserved)."""
    rw, perceive = _bidder()
    cf = _causal_fixture_field()

    def _seam(raw_question: str):
        tl = Timeline(); tl.record("utterance", raw_question or "", who="user")
        return BlockUniverse(tl, cf)

    monkeypatch.setattr(rw, "_shared_block_universe", _seam)

    causal_qs = [
        "What comes after nations consult?",
        "What typically follows when states consult and cooperate?",
        "What happens next after diplomacy?",
        "What ensues after an appeal?",
    ]
    fired = 0
    for q in causal_qs:
        cand = rw._temporal_candidate(perceive(q, []), q)
        if cand is not None:
            fired += 1
            assert cand.answer_kind == "temporal_projection"
            assert "a projection, not a certainty" in cand.answer     # hypothesis-tagged, hedged
    fire_rate = fired / len(causal_qs)
    assert fire_rate > 0.0, "temporal path must FIRE on clean causal queries (was ~0%)"

    # fail-closed preserved: unknown-token temporal questions still abstain
    for q in ("What comes after the zzzznonsense event?",
              "What follows the quarterly earnings webinar?"):
        assert rw._temporal_candidate(perceive(q, []), q) is None, q
