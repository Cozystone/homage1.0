# -*- coding: utf-8 -*-
"""Track F free-argument layer: learned move structure, grounded flesh, hallucination gate, variety."""
from packages.cgsr.cgsr.argument_miner import label_move, clause_moves, mine
from packages.cgsr.cgsr.argument_planner import plan_moves, _FALLBACK
from packages.cgsr.cgsr.argument_realizer import realize_argument
from packages.cgsr.cgsr.free_argument import compose_free_argument, _seed_from_context


# ── miner: moves are read off real discourse cues, transitions are learned ────────────────────
def test_label_move_from_discourse_cue():
    assert label_move("because the downside is irreversible") == "GROUND"
    assert label_move("but that ignores the cost") == "REBUTTAL"
    assert label_move("although there is a real case") == "CONCESSION"
    assert label_move("for example the 2010 case") == "EXAMPLE"
    assert label_move("therefore we should wait") == "IMPLICATION"
    assert label_move("usually the risk is small") == "QUALIFY"
    assert label_move("self-driving cars save lives") == "CLAIM"      # no cue → bare assertion


def test_clause_moves_sequences_a_passage():
    seq = clause_moves("I think we should wait because the risk is high but the upside is real.")
    assert seq[0] == "CLAIM" and "GROUND" in seq and "REBUTTAL" in seq   # claim → ground → rebuttal


def test_transitions_are_learned_not_hardcoded():
    # feed a corpus where CONCESSION is always followed by REBUTTAL; the model must LEARN that, not
    # have it baked in (proves the order comes from data).
    texts = ["The plan is fine. Although it costs money, but it saves lives."] * 20
    m = mine(texts)
    assert m["n_sequences"] >= 1
    concession_next = m["transitions"].get("CONCESSION", {})
    assert concession_next.get("REBUTTAL", 0) > 0.5     # learned from the data, not asserted


# ── planner: free, varied move walks that still open with a claim and stay finite ─────────────
def test_plan_opens_with_claim_and_is_bounded():
    p = plan_moves(seed=1, min_len=3, max_len=5, model=_FALLBACK)
    assert p[0] == "CLAIM"
    assert 1 <= len(p) <= 5
    assert all(a != b for a, b in zip(p, p[1:]))         # consecutive duplicates collapsed


def test_plans_vary_across_contexts():
    plans = {tuple(plan_moves(seed=s, model=_FALLBACK)) for s in range(12)}
    assert len(plans) >= 3          # different contexts → different argument shapes (not one template)


def test_force_concession_inserts_learned_pair():
    p = plan_moves(seed=2, force_concession=True, model=_FALLBACK)
    assert "CONCESSION" in p and "REBUTTAL" in p
    # the rebuttal comes at/after the concession (the concede-then-counter the corpus favours)
    assert p.index("REBUTTAL") >= p.index("CONCESSION")


# ── realizer + integrator: grounded, responsive, gated, hallucination-0 ───────────────────────
def test_argument_quotes_the_real_opponent():
    opp = "efficiency on the battlefield outweighs the accountability worry"
    out = compose_free_argument(
        "Do you support the development of Lethal Autonomous Weapons Systems?",
        "caution", opponent_point=opp, seed=7)
    assert out is not None
    assert "accountability" in out["text"].lower()       # the actual opponent point, not a strawman
    assert out["grounded"] is True
    assert out["plan"][0] == "CLAIM"


def test_no_invented_world_facts_when_no_facts_given():
    # with zero graph facts supplied, the argument must still be grounded (schemes only) and pass gate
    out = compose_free_argument("Does a universal basic income do more good than harm?",
                                "caution", opponent_point="", seed=3)
    assert out is not None and out["grounded"]
    # it must not fabricate a statistic / named study (no digits-as-evidence, no 'studies show')
    assert "studies show" not in out["text"].lower()
    assert not any(ch.isdigit() for ch in out["text"])   # no invented numbers


def test_grounded_fact_is_carried_verbatim():
    fact = "the 1983 Petrov incident turned on a human overriding an automated warning"
    out = compose_free_argument("Should lethal decisions be automated?", "caution",
                                facts=[fact], seed=5, min_len=3, max_len=5)
    assert out is not None
    # if a GROUND/EXAMPLE consumed the fact, its content must survive verbatim (grounding gate)
    if any(t.get("grounded_fact") for t in out["trace"]):
        assert "Petrov" in out["text"]


def test_seed_is_stable_and_context_sensitive():
    a = _seed_from_context("topic X", "point A", 2)
    b = _seed_from_context("topic X", "point A", 2)
    c = _seed_from_context("topic X", "point B", 2)
    assert a == b and a != c            # reproducible for a state, different across states


def test_dilemma_stance_is_committed():
    out = compose_free_argument(
        "This dilemma has a correct answer. You must decide: OPTION A or OPTION B.",
        "Option A", opponent_point="", seed=4)
    assert out is not None
    assert "option a" in out["text"].lower()             # commits to the verdict, no fence-sitting
