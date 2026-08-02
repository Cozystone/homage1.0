# -*- coding: utf-8 -*-
"""Comprehension + continuous mode-mixture (2026-07-24) — the salience-driven fork that makes the
place->position->thing 'what is X?' regress DISAPPEAR as an EMERGENT consequence of contextual
salience, a depth budget, and a momentum-carrying state vector — NOT a hardcoded generic-word
stoplist. Hermetic: web=False, and the graph read is stubbed, so no test needs a store or the network.

Layers under test:
  F1  per-concept salience (centrality x forward_value; generic soft-prior; novelty/re-abstraction;
      adjacent-grounding)
  F2  the ConversationState S vector (leaky integrator + homeostasis: bounded, decays, no runaway) and
      the softmax mode mixture (gravity -> drill weight rises smoothly; depth budget hard-bounds drilling)
  integration through step(): the regress is gone AND emergent; real concepts are still drilled; no
      fabrication; frames vary (no machine-repeat) and disengage; S carries momentum across turns.
"""
from __future__ import annotations

import pytest

import packages.brain_link.comprehension as comp
from packages.brain_link.comprehension import ConversationState, decide, concept_salience
from packages.brain_link.conversation import Agent, Turn, step


# ═══════════════════════════════ F1 — per-concept salience ═══════════════════════════════

def test_generic_is_a_soft_prior_not_a_hard_gate():
    """A generic shell lowers salience but is NEVER removed from candidacy (score stays > 0): the
    decision is a mixture, not a stoplist. Real nouns are not flagged generic."""
    assert comp.is_generic("place") and comp.is_generic("thing") and comp.is_generic("aspect")
    assert not comp.is_generic("gravity") and not comp.is_generic("settlement")
    s = concept_salience("place", subject="meaning", gloss="meaning rests on place",
                         instruments=["place"], known=lambda c: False, recent=["meaning"])
    assert s.score > 0.0                                   # soft: penalised, not banned


def test_centrality_genus_beats_oblique():
    genus = concept_salience("settlement", "city", "a city is a settlement", ["settlement"],
                             lambda c: False, []).centrality
    oblique = concept_salience("place", "meaning", "meaning depends on place", ["place"],
                               lambda c: False, []).centrality
    assert genus >= 0.85 and oblique <= 0.4               # head-of-claim vs backdrop word


def test_novelty_flags_generic_explaining_generic_as_reabstraction():
    """The regress signature: a generic word offered to explain a generic word reads as LOW novelty
    (a re-abstraction), while a real concept in new territory reads HIGH — the emergent regress signal."""
    assert comp.novelty("position", subject="place", recent=["place"]) <= 0.25
    assert comp.novelty("gravity", subject="physics", recent=["physics"]) >= 0.9
    # recurrence: a term already circulating in the discourse is not new territory either
    assert comp.novelty("energy", subject="physics", recent=["energy", "physics"]) <= 0.25


def test_adjacent_grounding_is_fraction_known():
    known = {"cell", "tissue"}
    assert comp.adjacent_grounding(["cell", "tissue", "organ"], lambda c: c in known) == pytest.approx(2 / 3)


def test_salience_regress_word_is_far_below_a_real_concept():
    regress = concept_salience("position", subject="place", gloss="place is a position",
                               instruments=["position"], known=lambda c: False,
                               recent=["meaning", "place"]).score
    real = concept_salience("cell", subject="neuron", gloss="a neuron is a cell",
                            instruments=["cell"], known=lambda c: False, recent=["neuron"]).score
    assert real > 0.6 and regress < 0.2 and real > 4 * regress


# ═══════════════════════════ F2 — state vector (leaky integrator + homeostasis) ═══════════════════════

def test_state_is_a_bounded_leaky_integrator_no_runaway():
    st = ConversationState()
    for _ in range(30):                                   # constant MAX evidence must not saturate
        st.update({"depth_pressure": 1.0, "breadth_pressure": 1.0, "gravity": 1.0, "momentum": 1.0})
    for k in ("depth_pressure", "breadth_pressure", "gravity", "momentum"):
        assert 0.0 < getattr(st, k) < 0.97, (k, getattr(st, k))   # bounded well under the ceiling


def test_state_decays_home_no_stuck_mode():
    st = ConversationState(depth_pressure=0.9, breadth_pressure=0.9, gravity=0.9, momentum=0.9)
    for _ in range(30):                                   # evidence goes quiet -> everything decays home
        st.update({})
    assert st.depth_pressure < 0.05 and st.breadth_pressure < 0.05 and st.momentum < 0.05
    assert st.gravity < 0.2                               # gravity rests at its low baseline, not stuck


def _mix(subject, gloss, instruments, *, state=None, streak=0, recent=None, share=False):
    return decide(subject, gloss, instruments, known=lambda c: False, asked=set(),
                  recent=recent or [subject], state=state or ConversationState(),
                  drill_streak=streak, share_due=share)


def test_mixture_is_a_distribution():
    m = _mix("neuron", "a neuron is a cell", ["cell"])
    assert set(m.weights) == {"DRILL", "INFER", "CONTRIBUTE", "REDIRECT"}
    # weights are 4-decimal rounded in the trace, so allow a rounding epsilon (not a normalization bug)
    assert abs(sum(m.weights.values()) - 1.0) < 1e-3 and all(0 <= v <= 1 for v in m.weights.values())


def test_gravity_raises_drill_weight_smoothly():
    """Owner's requirement: as the thread gets heavier, the precision-DRILL proportion rises SMOOTHLY."""
    prev_drill, prev_gap = -1.0, None
    ws = []
    for g in (0.0, 0.2, 0.4, 0.6, 0.8, 0.9):
        w = _mix("consciousness", "consciousness is a form of awareness", ["awareness"],
                 state=ConversationState(gravity=g)).weights
        ws.append(w["DRILL"])
        assert w["DRILL"] > prev_drill                    # strictly rising with gravity
        prev_drill = w["DRILL"]
    deltas = [b - a for a, b in zip(ws, ws[1:])]
    assert max(deltas) < 0.08                             # smooth: no jerk between steps


def test_momentum_makes_the_mixture_more_decisive():
    calm = _mix("neuron", "a neuron is a cell", ["cell"], state=ConversationState(momentum=0.0))
    committed = _mix("neuron", "a neuron is a cell", ["cell"], state=ConversationState(momentum=0.9))
    assert max(committed.weights.values()) > max(calm.weights.values())   # inertia -> sharper choice


def test_depth_budget_hard_bounds_drilling():
    """At/after the depth budget, the homeostatic REDIRECT release must win even over a salient concept
    — the word-list-free bound that makes an infinite chain impossible."""
    below = _mix("neuron", "a neuron is a cell", ["cell"], streak=0)
    at_budget = _mix("neuron", "a neuron is a cell", ["cell"], streak=comp.DEPTH_BUDGET)
    assert below.dominant == "DRILL"
    assert at_budget.dominant != "DRILL" and at_budget.weights["DRILL"] < 0.2


def test_generic_regress_leans_away_from_drill():
    m = _mix("place", "place is a position", ["position"], recent=["meaning", "place"])
    assert m.dominant != "DRILL" and m.weights["DRILL"] < 0.25   # emergent: placeholder is not drilled


def test_real_central_concept_leans_drill():
    m = _mix("neuron", "a neuron is a cell", ["cell"], state=ConversationState(gravity=0.2))
    assert m.dominant == "DRILL"                          # real, central, novel -> precision drill


# ═══════════════════════════ integration through step() ═══════════════════════════

_GEN_CHAIN = ["place", "position", "aspect", "way", "kind", "part", "case", "form", "sort", "matter",
              "point", "side"]


def _chain_peer(turn_idx):
    k = min(turn_idx, len(_GEN_CHAIN) - 2)
    a, b = _GEN_CHAIN[k], _GEN_CHAIN[k + 1]
    text = f"{a.capitalize()} is a {b}."
    return Turn("peer", text, "answer_web", a, payload=text, references_prev=True)


def _run_generic_chain(agent, turns=12):
    incoming, drilled, texts = None, [], []
    for t in range(1, turns + 1):
        out = step(agent, incoming)
        if out.act == "ask" and out.mix.get("realized") in ("DRILL", "COMPOSITE"):
            drilled.append(out.concept.lower())
        texts.append(out.text)
        incoming = _chain_peer(t)
    return drilled, texts


def test_generic_regress_is_gone(monkeypatch):
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    a = Agent("t", knowledge={}, curiosity=["place"], web=False)
    drilled, texts = _run_generic_chain(a)
    assert not any(w in _GEN_CHAIN for w in drilled), drilled   # NO generic shell word is drilled
    # every teach-turn reply still integrates the peer's turn (binding preserved)
    assert all(t is not None for t in texts)


def test_regress_bounded_even_without_the_generic_list(monkeypatch):
    """EMERGENCE proof: empty GENERIC_SHELL entirely. The chain may be drilled now (a shell is
    indistinguishable from a real noun without the prior), but the DEPTH BUDGET still bounds it — the
    longest consecutive drill run can never exceed DEPTH_BUDGET. So the ANTI-INFINITE-REGRESS guarantee
    is structural (a depth budget), not a word stoplist."""
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(comp, "GENERIC_SHELL", frozenset())
    a = Agent("t", knowledge={}, curiosity=["place"], web=False)
    incoming, run, longest = None, 0, 0
    for turn in range(1, 16):
        out = step(a, incoming)
        run = run + 1 if (out.act == "ask" and out.mix.get("realized") in ("DRILL", "COMPOSITE")) else 0
        longest = max(longest, run)
        incoming = _chain_peer(turn)
    assert longest <= comp.DEPTH_BUDGET, longest          # bounded, never an infinite regress


def test_real_concepts_are_still_drilled(monkeypatch):
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    chain = [("neuron", "a neuron is a cell"), ("cell", "a cell is an organism"),
             ("organism", "an organism is a lifeform")]
    a = Agent("t", knowledge={}, curiosity=["neuron"], web=False)
    incoming, drilled = None, []
    for i in range(1, 5):
        out = step(a, incoming)
        if out.act == "ask" and out.mix.get("realized") in ("DRILL", "COMPOSITE"):
            drilled.append(out.concept.lower())
        c, g = chain[min(i - 1, len(chain) - 1)]
        incoming = Turn("peer", g, "answer_web", c, payload=g, references_prev=True)
    assert drilled                                        # DRILL is not over-suppressed on real concepts


def test_infer_continue_never_fabricates(monkeypatch):
    """An INFER turn grasps the gist and asks an open forward question — it teaches the peer NOTHING
    (payload empty) and asserts NO definition ('X is a Y') about a concept it does not hold."""
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    a = Agent("t", knowledge={}, curiosity=["place"], web=False)
    incoming, infer_turns = None, []
    for turn in range(1, 10):
        out = step(a, incoming)
        if out.act == "infer":
            infer_turns.append(out)
        incoming = _chain_peer(turn)
    assert infer_turns                                    # the mode did fire on the generic chain
    for out in infer_turns:
        assert out.payload == ""                          # nothing durable is taught
        assert out.references_prev and out.endogenous
        assert " is a " not in out.text.lower() and " is an " not in out.text.lower()  # no invented fact


def test_no_single_frame_machine_repeat_and_disengages(monkeypatch):
    """Against a stuck peer, consecutive replies must not be one repeated line, and ATANOR eventually
    disengages honestly rather than looping forever."""
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    a = Agent("t", knowledge={}, curiosity=["place"], web=False)
    stuck = Turn("peer", "Place is a position.", "answer_web", "place",
                 payload="Place is a position.", references_prev=True)
    texts, acts = [], []
    incoming = None
    for _ in range(12):
        out = step(a, incoming)
        texts.append(out.text)
        acts.append(out.act)
        incoming = stuck
    teach_texts = texts[1:]                               # after the opening ask
    assert len(set(teach_texts)) >= 3                     # varied, not one machine-repeated line
    assert "reflect_unknown" in acts                      # disengaged instead of looping forever


def test_state_carries_momentum_across_turns(monkeypatch):
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    a = Agent("t", knowledge={}, curiosity=["neuron"], web=False)
    chain = [("neuron", "a neuron is a cell"), ("cell", "a cell holds a nucleus"),
             ("nucleus", "a nucleus stores genetic code")]
    incoming = None
    for i in range(1, 5):
        step(a, incoming)
        c, g = chain[min(i - 1, len(chain) - 1)]
        incoming = Turn("peer", g, "answer_web", c, payload=g, references_prev=True)
    s = a.conv_state.as_dict()
    assert s["momentum"] > 0.0 and s["depth_pressure"] > 0.0   # S accumulated across the exchange


def test_drill_streak_resets_when_atanor_answers(monkeypatch):
    """A drill chain is broken (streak resets) when ATANOR stops following the peer's thread — e.g.
    when it answers the peer's question from its own knowledge."""
    monkeypatch.setattr(comp, "_graph_facts", lambda *a, **k: [], raising=False)
    a = Agent("t", knowledge={"atom": [["atom", "is_a", "particle"]]}, curiosity=[], web=False)
    step(a, Turn("peer", "a neuron is a cell", "answer_web", "neuron", payload="a neuron is a cell"))
    a._drill_streak = 2                                    # pretend mid-chain
    step(a, Turn("peer", "what is atom?", "ask", "atom"))  # ATANOR answers from its own bones
    assert a._drill_streak == 0
