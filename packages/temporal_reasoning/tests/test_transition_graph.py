# -*- coding: utf-8 -*-
"""Sealed gates for the event-transition-graph reasoner (2026-07-23).

The measured problem (after commit 34fdd88a): the block-universe temporal bidder fired ~75% on
step-1 causal queries once the typed causal edges re-ranked the step-1 successor — but ONLY step-1,
because the multi-step walk still climbed the 1-D LEARNED phase coordinate. A 1-D coordinate is
structurally too weak for multi-step causal reasoning:
  (1) it has a single maximum, so every monotone chain FUNNELS to that global phase-argmax sink;
  (2) it cannot represent CYCLES (a monotone coordinate never revisits a node);
  (3) it is direction-blind to real successors that sit EARLIER on the line (return/de-escalation
      edges) and to phase-adjacent top edges dropped by the confidence-margin gate.

The fix (packages/temporal_reasoning/transition_graph.py): walk the typed causal edges DIRECTLY as a
Markov transition graph — successor(e) = observed-count distribution over next events; confidence =
posterior_direction(n_ab, n_ba) (NOT the phase sigmoid); sense-aware via ctx where available; the 1-D
phase demoted to a count-tie tiebreak. Walks may revisit nodes (cycles) and stop fail-closed.

These gates are deterministic on hand-built fixtures (a, b, ctx) and on the REAL mined store (c).
Gate (d) — no regression — is the whole suite passing plus the bidder-contract lock below.
"""
from __future__ import annotations

import math
from collections import Counter

import pytest

from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.precedence_field import PrecedenceField, posterior_direction
from packages.temporal_reasoning.transition_graph import EventTransitionGraph, DEFAULT_MARGIN
from packages.temporal_reasoning.unified_timeline import Timeline


def _monotone_phase_walk(phase: dict[str, float], start: str, horizon: int = 6) -> list[str]:
    """What a 1-D phase coordinate ALONE dictates (the pre-graph behavior): at each step jump to the
    nearest token strictly AHEAD in phase. A single maximum => every chain funnels to argmax(phase);
    a monotone coordinate can never revisit a node. This is the object the graph walk is contrasted
    against."""
    cur, chain, seen = start, [start], {start}
    for _ in range(horizon):
        ahead = [(t, p) for t, p in phase.items() if p > phase[cur] and t not in seen]
        if not ahead:
            break
        nxt = min(ahead, key=lambda tp: tp[1] - phase[cur])[0]
        chain.append(nxt)
        seen.add(nxt)
        cur = nxt
    return chain


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (a): no global-sink funnel — the graph follows the real high-count path; the old phase walk
#           funnels to the phase-argmax and cannot take the real (phase-behind) successor.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _sink_and_return_field() -> PrecedenceField:
    """The two real failure shapes of the 1-D phase, in one fixture:
      * `ret` is `start`'s REAL top-count successor (100) but sits BEHIND start in phase — an ahead-
        only monotone walk can NEVER take it;
      * `argmax` is a lone phase-maximum decoy reachable only by a rare edge (count 1) — the monotone
        walk funnels there through the phase decoy `mid` and dies.
    The real path is a clean forward-dominant cycle start -> ret -> q -> start (each reverse count 0,
    so each edge's posterior_direction is high). The graph ignores phase for selection and walks it,
    never touching the sink."""
    phase = {"start": 0.0, "mid": 0.5, "argmax": 1.0, "ret": -1.0, "q": -0.5}
    pairs = {("start", "ret"): 100, ("ret", "q"): 90, ("q", "start"): 80, ("start", "argmax"): 1}
    return PrecedenceField(phase=phase, seen={t: 50 for t in phase},
                           event_vocab=set(phase), causal_pairs=pairs)


def test_gate_a_graph_follows_real_path_no_global_sink_funnel():
    f = _sink_and_return_field()
    argmax = max(f.phase, key=f.phase.get)
    assert argmax == "argmax", "the fixture's global phase maximum is the sink the old walk funnels to"
    # the real top successor is PHASE-BEHIND the anchor (the structural reason the monotone walk misses it)
    assert f.phase["ret"] < f.phase["start"]

    g = EventTransitionGraph.from_field(f)
    steps = g.walk_forward("start", horizon=4)
    after = ["start"] + [s["event_token"] for s in steps]

    # follows the REAL high-count path (start->ret, count 100), NOT the rare edge to the sink
    assert after[1] == "ret", after
    assert "argmax" not in after, after                 # never funnels to the global phase-sink
    # and it genuinely branches through real structure, revisiting a node (a cycle) on the way
    assert len(set(after)) < len(after), after          # some node recurs -> real branching structure

    # contrast: the 1-D monotone phase walk on the SAME phase field funnels to the argmax sink and can
    # never take the phase-behind real successor
    mono = _monotone_phase_walk(f.phase, "start")
    assert mono[-1] == "argmax", mono                   # funnels to the single global maximum
    assert "ret" not in mono                            # the real top successor is invisible to it
    assert len(set(mono)) == len(mono)                  # monotone => no revisit


def test_gate_a_holds_through_the_production_project_forward_surface():
    f = _sink_and_return_field()
    tl = Timeline(); tl.record("utterance", "what comes after the start event?", who="user")
    proj = BlockUniverse(tl, f).project_forward(horizon=3)
    toks = [p["event_token"] for p in proj]
    assert proj and toks[0] == "ret"                    # the real successor, surfaced by the graph
    assert "argmax" not in toks                         # not the phase-sink
    assert all(p["hypothesis"] is True for p in proj)   # still hypothesis-tagged
    assert all(p["confidence"] >= DEFAULT_MARGIN for p in proj)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (b): cycles are representable — a cyclic fixture is walked as a cycle (a node recurs), not
#           truncated by a monotone coordinate.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _cyclic_field() -> PrecedenceField:
    """A pure 3-cycle plan -> build -> ship -> plan (tokens >= 3 chars so the surface tokenizer sees
    them). Bradley-Terry cannot satisfy a cyclic order, so any 1-D phase it fits is self-contradictory
    — exactly why the coordinate cannot express the loop."""
    pairs = {("plan", "build"): 10, ("build", "ship"): 10, ("ship", "plan"): 10}
    f = PrecedenceField.fit(Counter(pairs), min_count=1)
    f.event_vocab = set(f.phase)
    f.causal_pairs = dict(pairs)
    return f


def test_gate_b_cycle_is_walked_not_truncated():
    f = _cyclic_field()
    g = EventTransitionGraph.from_field(f)
    steps = g.walk_forward("plan", horizon=3)
    seq = ["plan"] + [s["event_token"] for s in steps]
    assert seq == ["plan", "build", "ship", "plan"], seq   # the loop closes: plan RECURS
    assert seq.count("plan") == 2                           # a node recurs -> cycle, not truncation

    # contrast: the 1-D monotone phase walk cannot revisit -> it truncates before closing the loop
    mono = _monotone_phase_walk(f.phase, "plan", horizon=6)
    assert mono.count("plan") == 1, mono                    # single-visit; the cycle is unrepresentable
    assert mono != seq


def test_gate_b_cycle_survives_the_production_project_forward_surface():
    f = _cyclic_field()
    tl = Timeline(); tl.record("utterance", "what comes after we plan?", who="user")
    proj = BlockUniverse(tl, f).project_forward(horizon=3)
    full = ["plan"] + [p["event_token"] for p in proj]
    assert full == ["plan", "build", "ship", "plan"], full
    assert proj[-1]["event_token"] == "plan"                # the anchor recurs -> the cycle is surfaced
    assert all(p["hypothesis"] is True for p in proj)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (c): fire-rate preserved + multi-step meaningful, on the REAL mined typed-causal edges.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _real_field() -> PrecedenceField:
    from packages.temporal_reasoning.causal_corpus import _causal_pairs
    pairs = _causal_pairs(min_count=2)
    if not pairs:
        pytest.skip("no mined causal store (data/temporal_reasoning/causal_counts.json) in this env")
    f = PrecedenceField.fit(Counter(pairs), min_count=1)
    f.event_vocab = set(f.phase)
    f.causal_pairs = dict(pairs)
    return f


_CAUSAL_QS = [
    "What comes after nations consult?",
    "What happens next after diplomacy?",
    "What ensues after an appeal?",
    "What comes after an assault?",
    "What follows a demand?",
    "What comes next after a conflict?",
    "What typically follows intent?",
    "What comes after states disapprove?",
]


def test_gate_c_fire_rate_stays_high_through_the_live_bidder(monkeypatch):
    """Drive the ACTUAL workspace bidder over the real mined causal edges. Fire-rate on clean causal
    queries must stay >= the committed 75% (the payoff is preserved), and unknown-token queries must
    still abstain (fail-closed)."""
    f = _real_field()
    import packages.cgsr.cgsr.response_workspace as rw
    from packages.cgsr.cgsr.comprehension import perceive

    def _seam(raw_question: str):
        tl = Timeline(); tl.record("utterance", raw_question or "", who="user")
        return BlockUniverse(tl, f)

    monkeypatch.setattr(rw, "_shared_block_universe", _seam)

    fired = 0
    for q in _CAUSAL_QS:
        cand = rw._temporal_candidate(perceive(q, []), q)
        if cand is not None:
            fired += 1
            assert cand.answer_kind == "temporal_projection"
            assert "a projection, not a certainty" in cand.answer   # hedged, hypothesis-tagged
    rate = fired / len(_CAUSAL_QS)
    assert rate >= 0.75, f"fire-rate {rate:.0%} fell below the committed 75%"

    # fail-closed: genuinely unknown temporal questions still abstain
    for q in ("What comes after the zzzznonsense event?", "What follows the quarterly webinar?"):
        assert rw._temporal_candidate(perceive(q, []), q) is None, q


def test_gate_c_multistep_surfaces_real_successors_with_real_confidence():
    """A 2-3 step projection walks the REAL observed successors with real confidence, every item
    hypothesis-tagged, and it is a genuine chain (each step anchors on the previous target)."""
    f = _real_field()
    tl = Timeline(); tl.record("utterance", "what comes after nations consult?", who="user")
    proj = BlockUniverse(tl, f).project_forward(horizon=3)

    assert len(proj) >= 2, "multi-step projection fires (was step-1 only)"
    assert proj[0]["event_token"] == "diplomacy"        # consult's top observed successor (count 149)
    assert all(p["confidence"] >= DEFAULT_MARGIN for p in proj), proj
    assert all(p["hypothesis"] is True for p in proj)
    # every surfaced step is a REAL observed edge (positive mined count), never a phase-nearest guess
    assert all(p.get("count", 0) > 0 for p in proj), proj
    # a genuine chain: step k+1 departs from step k's target
    for a, b in zip(proj, proj[1:]):
        assert b["after"] == a["event_token"]


def test_gate_c_confidence_is_posterior_direction_not_the_phase_sigmoid():
    f = _real_field()
    g = EventTransitionGraph.from_field(f)
    edge = next(e for e in g.successors("consult") if e.target == "diplomacy")
    n_ab = f.causal_pairs[("consult", "diplomacy")]
    n_ba = f.causal_pairs.get(("diplomacy", "consult"), 0)
    # the edge confidence IS the directed posterior, NOT the 1-D phase sigmoid
    assert edge.confidence == pytest.approx(posterior_direction(n_ab, n_ba), abs=1e-9)
    phase_sigmoid = 1.0 / (1.0 + math.exp(-(f.phase["diplomacy"] - f.phase["consult"])))
    assert abs(edge.confidence - phase_sigmoid) > 0.01, "posterior must differ from the phase sigmoid"


def test_gate_c_backward_is_routed_through_the_graph_and_fails_closed():
    f = _real_field()
    tl = Timeline()
    back = BlockUniverse(tl, f).infer_backward("diplomacy", k=3)
    assert back, "the graph grounds observed predecessors of diplomacy"
    # predecessors are real observed priors (e.g. consult -> diplomacy is the biggest, 149)
    assert any(b["event_token"] == "consult" for b in back)
    assert all(b["confidence"] >= DEFAULT_MARGIN and b["hypothesis"] is True for b in back)
    # fail-closed on an unknown token
    assert BlockUniverse(tl, f).infer_backward("zzzznonsense") == []


# ── GATE (c) sense-awareness: ctx conditioning overrides the global order WHERE AVAILABLE ────────────

def test_gate_c_ctx_conditioning_is_sense_aware():
    """The global corpus orders aid before appeal (5:1). A query context word 'crisis' carries the
    OPPOSITE evidence (appeal before aid, 8:0). Under that context the graph flips the confident
    direction — sense-aware order, not the corpus average."""
    pairs = {("aid", "appeal"): 5, ("appeal", "aid"): 1}
    ctx = {("crisis", "appeal", "aid"): 8}          # under 'crisis', appeal precedes aid
    g = EventTransitionGraph(pairs, event_vocab={"aid", "appeal"}, ctx=ctx)

    # global: aid -> appeal is confident (posterior 6/8 = 0.75); appeal has NO confident successor
    assert [e.target for e in g.successors("aid")] == ["appeal"]
    assert g.successors("appeal") == []                          # global appeal->aid is 2/8 = 0.25

    # context 'crisis': appeal -> aid becomes the confident successor, tagged as ctx-sourced
    sc = g.successors("appeal", ctx_tokens=["crisis"])
    assert sc and sc[0].target == "aid"
    assert sc[0].source == "ctx" and sc[0].confidence > 0.8
    # an unrelated context word carries no evidence -> falls back to the (weak) global -> abstains
    assert g.successors("appeal", ctx_tokens=["unrelated"]) == []


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (d): no regression — the bidder-contract keys the workspace reads are preserved verbatim.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_gate_d_bidder_contract_keys_preserved():
    f = _real_field()
    tl = Timeline(); tl.record("utterance", "what comes after nations consult?", who="user")
    proj = BlockUniverse(tl, f).project_forward(horizon=3)
    for p in proj:                                              # response_workspace reads these keys
        assert {"step", "after", "event_token", "confidence", "hypothesis"} <= set(p)
        assert isinstance(p["confidence"], float) and 0.0 <= p["confidence"] <= 1.0
    back = BlockUniverse(tl, f).infer_backward("diplomacy", k=3)
    for b in back:
        assert {"before", "event_token", "confidence", "observed_on_timeline", "hypothesis"} <= set(b)


def test_gate_d_toy_phase_only_field_keeps_the_legacy_walk():
    """A field with NO typed causal edges (the toy/legacy case) must keep the original 1-D phase walk
    unchanged — the graph route only engages when causal_pairs are present."""
    toy = PrecedenceField(phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
                          seen={t: 5 for t in ("plant", "grow", "harvest", "eat")})
    assert toy.causal_pairs is None
    tl = Timeline(); tl.record("fact", "the crops grow through spring")
    proj = BlockUniverse(tl, toy).project_forward(horizon=2)
    assert [p["event_token"] for p in proj] == ["harvest", "eat"]   # legacy monotone phase walk intact
