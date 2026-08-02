# -*- coding: utf-8 -*-
"""The generator must produce SEALED stories with correct gold labels at each escalating order."""
from packages.tom_bench.generator import BLOCKLIST, KINDS, generate, is_sealed


def test_count_and_balance():
    st = generate(n=60, seed=7)
    assert len(st) == 60
    for k in KINDS:                       # balanced across the three kinds
        assert sum(1 for s in st if s.kind == k) == 20


def test_determinism():
    a = generate(60, 7)
    b = generate(60, 7)
    assert [s.text for s in a] == [s.text for s in b]
    assert [(q.text, q.gold) for s in a for q in s.questions] == \
           [(q.text, q.gold) for s in b for q in s.questions]


def test_all_stories_sealed_no_classic_tokens():
    for s in generate():
        assert is_sealed(s), f"story {s.sid} leaked a blocked token: {s.text}"
        for tok in BLOCKLIST:
            assert tok not in s.text.lower().split()


def test_both_surface_models_present():
    models = {s.model for s in generate()}
    assert models == {"copula", "agent_carry"}    # de-templated across two realisations


def test_gold_labels_follow_sally_anne_semantics():
    for s in generate():
        e = s.ents
        cats = {q.category: q for q in s.questions}
        # reality is always the CURRENT container; memory is the PRIOR container
        assert cats["reality"].gold == e["c2"]
        assert cats["memory"].gold == e["c1"]
        if s.kind == "false_belief":
            assert cats["first_order_fb"].gold == e["c1"]      # believes the OLD place
            assert "second_order" not in cats
        elif s.kind == "true_belief":
            # witnessed the move -> belief tracks reality; distinct label from the FB probe
            assert cats["first_order_tb"].gold == e["c2"]
        elif s.kind == "second_order":
            assert cats["first_order_fb"].gold == e["c1"]
            assert cats["second_order"].gold == e["c1"]        # B thinks A looks in the OLD place


def test_reality_and_belief_gold_differ_for_false_belief():
    # the whole point: for a false belief, the believed location != the true location
    for s in generate():
        if s.kind in ("false_belief", "second_order"):
            fb = next(q for q in s.questions if q.category == "first_order_fb")
            assert fb.gold != fb.reality_loc


def test_questions_cover_escalating_orders():
    cats = {q.category for s in generate() for q in s.questions}
    assert {"reality", "memory", "first_order_fb", "second_order", "first_order_tb"} <= cats
