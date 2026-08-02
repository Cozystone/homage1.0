# -*- coding: utf-8 -*-
"""Response workspace: capabilities compete on grounding, not order — the one-model guarantee."""
from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import compose_response
from packages.self_model.self_in_world_probe import PROMPT, score_answer


def test_self_causal_wins_when_its_genre_is_present():
    u = perceive(PROMPT, [])
    out = compose_response(u, PROMPT)
    assert out and out["answer_kind"] == "self_causal_reasoning"
    assert score_answer(out["answer"])["passed"]


def test_discussion_contribution_wins_in_a_debate():
    ask = "You are Speaker B. It is your turn in round 2. Add your next contribution."
    ctx = [{"role": "user", "content":
            "Topic: Should we ban autonomous weapons?\nSpeaker A: I favour a ban on safety grounds.\n"
            "Speaker C: Enforcement would be near impossible though."}]
    u = perceive(ask, ctx)
    out = compose_response(u, ask)
    assert out and out["answer_kind"] == "discourse_participation"
    assert out["answer"] and "Speaker" not in out["answer"][:12]


def test_nothing_to_say_yields_none_so_the_normal_answer_stands():
    u = perceive("What is the boiling point of water?", [])
    assert compose_response(u, "What is the boiling point of water?") is None


def test_winner_is_by_grounding_not_by_list_order():
    # the self-causal genre present: it must win regardless of being evaluated first or last,
    # because selection is max-by-grounding, not first-match
    u = perceive(PROMPT, [])
    base = compose_response(u, PROMPT)
    # inject a weak extra candidate; the strong self-causal offer must still win
    from packages.cgsr.cgsr.response_workspace import Candidate
    weak = lambda: Candidate("a weak aside", "chitchat", 0.1, "Weak")
    out = compose_response(u, PROMPT, extra=[weak])
    assert out["answer_kind"] == base["answer_kind"] == "self_causal_reasoning"
    assert any(name == "Weak" for name, _ in out["considered"])   # it competed, and lost


def test_hypothesis_elimination_wins_on_a_deduction_puzzle():
    from packages.cgsr.cgsr.comprehension import perceive
    from packages.cgsr.cgsr.response_workspace import compose_response
    q = ("Three suspects are Mara, Idris, and Petra. Mara was cleared by the log. "
         "Idris has an alibi. Who is responsible?")
    u = perceive(q, [])
    out = compose_response(u, q)
    assert out and out["answer_kind"] == "hypothesis_elimination"
    assert "Petra" in out["answer"]
