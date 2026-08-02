# -*- coding: utf-8 -*-
"""fluency_v1 benchmark: faithfulness stays ~1.0 (no fabrication) BEFORE and AFTER, slot-copy is
perfect on the AFTER path, and the fluency proxy improves — with the gain honestly concentrated on
multi-fact answers (run-on reduction) and identical on sparse answers."""
from packages.fluency import fluency_v1 as F


def test_benchmark_has_enough_tasks():
    assert len(F.tasks()) >= 28


def test_faithfulness_is_one_before_and_after():
    """The anti-fabrication invariant: every variant traces every content word to the grounding."""
    rep = F.run()
    for variant, m in rep["aggregate"].items():
        assert m["faithfulness"] == 1.0, (variant, m)


def test_after_slot_copy_is_perfect():
    rep = F.run()
    for variant in ("after_simple", "after_neutral", "after_explanatory", "after_auto"):
        assert rep["aggregate"][variant]["slot_copy"] == 1.0, variant


def test_fluency_proxy_improves_after():
    rep = F.run()
    agg = rep["aggregate"]
    before = agg["before"]["fluency_proxy"]
    assert agg["after_auto"]["fluency_proxy"] >= before
    assert agg["after_neutral"]["fluency_proxy"] >= before
    assert agg["after_explanatory"]["fluency_proxy"] >= before


def test_gain_is_on_multi_fact_boundary():
    """Honest boundary: delex+copy+register helps multi-fact answers and is identical on sparse
    (<=2 bones) answers — that is exactly the sub-class it helps."""
    rep = F.run()
    b = rep["boundary"]
    assert b["proxy_after_auto_multi"] > b["proxy_before_multi"]     # real gain where run-ons live
    assert b["proxy_after_auto_sparse"] == b["proxy_before_sparse"]  # untouched where content is thin


def test_multi_subject_fixes_referential_drop():
    """frame_realizer conflates a second distinct subject into 'It' and drops that entity; the AFTER
    path keeps it (a real slot-copy improvement, not just a proxy one)."""
    bones = [["dog", "is_a", "mammal"], ["dog", "capable_of", "bark"],
             ["cat", "is_a", "mammal"], ["cat", "capable_of", "purr"]]
    from packages.realizer_struct.frame_realizer import realize as before
    from packages.fluency.realizer import realize as after
    assert F.slot_copy_accuracy(bones, before(bones)) < 1.0          # 'cat' lost to 'It'
    assert F.slot_copy_accuracy(bones, after(bones)) == 1.0          # 'cat' preserved
    assert "cat" in after(bones).lower()


def test_faithfulness_scorer_catches_a_planted_fabrication():
    """Guard the scorer itself: an invented word that does not trace to grounding is flagged, so the
    1.0 faithfulness numbers above are meaningful, not vacuous."""
    from packages.fluency.delex import Grounding
    grounding = Grounding.from_bones([["coffee", "is_a", "beverage"]])
    faith, fab = F.faithfulness("Coffee is a beverage made of cheese.", grounding)
    assert faith < 1.0 and "cheese" in fab
