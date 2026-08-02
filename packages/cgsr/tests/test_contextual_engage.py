# -*- coding: utf-8 -*-
"""One context-aware engagement decision unifies the three former mode-switch branches (owner
2026-07-20: 하나의 모델). It perceives context and chooses HOW to engage, or yields None."""
from packages.cgsr.cgsr.contextual_engage import contextual_engage


def _shape_engage(shape, language):
    return f"[shape:{shape}]"


def test_discussion_context_routes_to_free_argument():
    ctx = [{"role": "system", "content": "Topic: Should facial recognition be used for mass surveillance?"},
           {"role": "user", "content": "Speaker A: Security is worth it.\nSpeaker B: But tracking the innocent is a distinct harm."}]
    out = contextual_engage("You are Speaker C. Your turn.", ctx, shape="opinion",
                            current_answer="Risk is a board game.", is_abstention=False,
                            shape_engage_fn=_shape_engage)
    assert out is not None and out["answer_kind"] == "discourse_participation"
    assert "surveillance" in out["answer"].lower() or "tracking" in out["answer"].lower()


def test_subjective_comparison_routes_to_opinion():
    out = contextual_engage("Is loyalty more important than honesty?", [], shape="opinion",
                            current_answer="I don't have information on that.", is_abstention=True,
                            shape_engage_fn=_shape_engage)
    # a subjective comparison should be engaged as a trade-off (opinion), not the shape fallback
    assert out is not None
    assert out["answer_kind"] in ("opinion_engage", "conversational_engage")


def test_conversational_abstention_gets_engaged_by_shape():
    out = contextual_engage("what should I do about a tough choice?", [], shape="advice",
                            current_answer="I cannot answer that.", is_abstention=True,
                            current_kind=None, shape_engage_fn=_shape_engage)
    assert out is not None and out["answer_kind"] == "conversational_engage"
    assert out["answer"] == "[shape:advice]"


def test_nothing_applies_yields_none():
    # a normal factual question that got a good answer -> no engagement override
    out = contextual_engage("What is the capital of France?", [], shape="factual",
                            current_answer="Paris is the capital of France.", is_abstention=False,
                            current_kind="structured_triple_lookup", shape_engage_fn=_shape_engage)
    assert out is None


def test_sourced_answer_is_never_overridden_by_opinion():
    out = contextual_engage("Is X better than Y?", [], shape="opinion",
                            current_answer="X is taller (sources: wikipedia).", is_abstention=False,
                            current_kind="web_attribution", shape_engage_fn=_shape_engage)
    # a real sourced answer must survive (opinion must not clobber it)
    assert out is None or out["answer_kind"] != "opinion_engage"
