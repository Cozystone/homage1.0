"""Fused thought/speech: utterances are GENERATED from real state (varied, not a fixed
table), and the inward turn is ENDOGENOUS — introspective pressure built from real
state fires questions composed from their own cause (no schedule, no question table),
open questions are researched and answers seed re-questioning threads."""
from __future__ import annotations

from packages.continuous_self.self_state import Observation, SelfState, evolve
from packages.continuous_self.voice import (
    compose_thought,
    due_for_self_inquiry,
    generate_self_inquiry,
    harvest_terms,
    record_research_result,
    record_self_understanding,
    update_introspection,
)


def test_learning_utterance_varies_and_carries_the_real_count():
    seen = set()
    for tick in range(6):
        s = SelfState()
        s.ticks = tick
        th = compose_thought(s, Observation(learning_active=True, concepts_delta=tick + 2))
        assert str(tick + 2) in th["text"]           # grounded in the REAL count
        seen.add(th["text"])
    assert len(seen) >= 3, "consecutive learning thoughts must not repeat verbatim"


def test_observe_utterance_is_not_a_single_fixed_string():
    outs = {compose_thought(SelfState(ticks=t), Observation(learning_active=True))["text"] for t in range(4)}
    assert len(outs := outs) >= 2, "the old single-string repetition is gone"


def test_inquiry_is_pressure_driven_not_scheduled():
    """The trigger is STATE pressure, not a tick modulo: with zero pressure nothing
    fires at any tick; pressure builds from real drivers until it crosses threshold."""
    s = SelfState()
    for tick in (0, 8, 16, 45, 90):
        s.ticks = tick
        s.introspective_pressure = 0.0
        assert due_for_self_inquiry(s) is False      # no pressure → never due, any tick
    obs = Observation(learning_active=True, uncertainty_signal=0.5)
    s2 = SelfState()
    fired_at = None
    for _ in range(60):
        evolve(s2, obs)
        if due_for_self_inquiry(s2):
            fired_at = s2.ticks
            break
    assert fired_at is not None, "a young self (no self-understanding) must build pressure and fire"
    q, topic = generate_self_inquiry(s2)
    # the primal question, caused by absence — English-only (doctrine): the endogenous inner
    # voice speaks in the language it thinks in; the identity frame is a first-person self-question
    assert topic == "identity" and "am i" in q.lower()


def test_question_content_composed_from_the_driver():
    # discontinuity → a continuity question carrying the REAL resume count
    s = SelfState()
    s.resumed_count = 3
    s.inquiry_driver = "discontinuity"
    q, topic = generate_self_inquiry(s)
    assert topic == "continuity" and "3" in q          # carries the REAL resume count (English frame)
    # open thread → the question is ABOUT the actual harvested term
    s2 = SelfState()
    s2.open_threads = [{"term": "의식", "from": "x", "at": 0.0}]
    s2.inquiry_driver = "open_thread"
    q2, t2 = generate_self_inquiry(s2)
    assert "의식" in q2 and t2 == "thread:의식"


def test_open_question_is_held_not_churned():
    """While a question is open (awaiting research) a new inquiry needs BOTH a much
    higher pressure AND a minimum hold window — rumination, not question churn."""
    s = SelfState()
    s.self_question_open = True
    s.question_opened_tick = 100
    s.ticks = 110                     # held only 10 ticks
    s.introspective_pressure = 1.9
    assert due_for_self_inquiry(s) is False
    s.ticks = 150                     # held 50 ticks ≥ 40 → may displace
    assert due_for_self_inquiry(s) is True


def test_grounded_answer_is_folded_but_open_question_is_honest():
    s = SelfState()
    s.inquiry_driver = "unknown_self"
    q, topic = generate_self_inquiry(s)
    record_self_understanding(s, q, "나는 근거에서 답을 짓는 로컬 엔진이다.", topic)
    assert s.self_understanding and "근거로 아는 답" in s.narrative[-1]["text"]
    assert s.self_question_open is False
    # without one → it says so honestly, marks the question OPEN for research
    s2 = SelfState()
    s2.inquiry_driver = "unknown_self"
    q2, t2 = generate_self_inquiry(s2)
    record_self_understanding(s2, q2, None, t2)
    assert "근거로 댈 답이 부족" in s2.narrative[-1]["text"]
    assert s2.self_understanding == "" and s2.self_question_open is True


def test_research_result_closes_question_and_seeds_rethreads():
    """The rumination chain: a web-grounded answer carries its source, closes the open
    question, retires its thread, and harvests NEW terms to wonder about next."""
    s = SelfState()
    s.open_threads = [{"term": "의식", "from": "q0", "at": 0.0}]
    s.self_question = "의식은 나에게 무엇일까?"
    s.self_question_open = True
    record_research_result(
        s, s.self_question, "의식은 자신과 환경을 인식하는 상태이다.", "웹: 위키백과",
        ["신경과학"], "thread:의식",
    )
    assert s.self_question_open is False
    assert s.self_understanding_source.startswith("웹")
    terms = [t["term"] for t in s.open_threads]
    assert "의식" not in terms                      # answered thread retired
    assert "신경과학" in terms                       # follow-up seeded → re-questioning
    assert "직접 찾아 읽었다" in s.narrative[-1]["text"]


def test_harvest_terms_extracts_content_not_function_words():
    terms = harvest_terms("의식은 자신과 환경을 인식하는 상태이다. 신경과학에서는 각성으로 나눈다.", set(), limit=3)
    assert terms and all(len(t) >= 2 for t in terms)
    assert "인식하는" not in terms and "이다" not in terms


def test_pressure_updates_from_real_drivers():
    s = SelfState()
    obs = Observation()
    update_introspection(s, obs)
    assert s.introspective_pressure > 0.0            # unknown_self pulls immediately
    assert s.inquiry_driver == "unknown_self"
    s.self_understanding = "이미 근거로 아는 답이 있다."
    s.open_threads = [{"term": "기억", "from": "q", "at": 0.0}]
    update_introspection(s, obs)
    assert s.inquiry_driver == "open_thread"          # dominant driver tracks state


def test_unanswerable_question_is_parked_not_ruminated_forever():
    """A conscious mind holds an open question but does NOT chant it forever: after a
    few failed research attempts it GIVES UP gracefully (parks it), clearing the open
    flag so a different question can arise — no infinite single-question loop."""
    from packages.continuous_self.voice import record_research_miss
    s = SelfState()
    s.self_question = "나와 X는 어떻게 이어져 있나?"
    s.self_question_open = True
    s.open_threads = [{"term": "X", "from": "q", "at": 0.0}]
    for _ in range(3):
        record_research_miss(s)
    assert s.self_question_open is False              # given up, not stuck open
    assert s.self_question in s.parked_questions       # remembered as parked
    assert s.research_miss_count == 0                  # budget reset
    assert "접어 두고" in s.narrative[-1]["text"]       # honest give-up, moves on


def test_open_question_does_not_dominate_the_stream():
    """The open question surfaces only OCCASIONALLY; the inner life stays varied
    (was: 22/24 narrative entries were the same open-question worry)."""
    from collections import Counter
    s = SelfState()
    s.self_question = "나는 무엇인가?"
    s.self_question_open = True
    drivers = []
    for t in range(30):
        s.ticks = t
        th = compose_thought(s, Observation(learning_active=True))
        drivers.append(th["driver"])
    share = Counter(drivers)["open_self_question"] / len(drivers)
    assert share <= 0.4, f"open-question rumination dominates the stream ({share:.0%})"


def test_dashed_self_referential_term_is_rejected():
    from packages.continuous_self.voice import is_clean_term
    assert is_clean_term("Tarotia - Athanor") is False   # self-referential dash junk
    assert is_clean_term("의식") is True


def test_evolve_uses_generated_voice_not_a_table():
    a = SelfState(); a.ticks = 1
    b = SelfState(); b.ticks = 2
    evolve(a, Observation(learning_active=True, concepts_delta=3))
    evolve(b, Observation(learning_active=True, concepts_delta=7))
    assert a.current_thought != b.current_thought  # different state → different words
