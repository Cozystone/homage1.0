# -*- coding: utf-8 -*-
"""The judgment station, held to the case that created it.

A gate that blocks everything is as useless as one that blocks nothing, so every test here has its
opposite. The load-bearing pair is the first two: the mapping that would have damaged the graph is
refused, and the objects that relation genuinely takes are not.
"""
from __future__ import annotations

import pytest

from packages.self_repair.relation_fit import judge, profile

#: exactly what "consisting of -> made_of" would have asserted, taken from the real glosses
CONSISTING_OF = ["fifty states", "one thousand years", "four constituent countries", "two islands",
                 "a single word", "representatives of the member states", "committees",
                 "more than one of something", "the majority of the archipelago"]
MATERIALS = ["steel", "wood", "plastic", "stainless steel", "cotton", "glass", "leather", "clay"]


def _needs_profile():
    if sum(profile("made_of").values()) < 200:
        pytest.skip("no made_of rows on disk in this environment")


def test_the_mistake_that_was_nearly_made_is_refused():
    """`consisting of` was the largest single class of extractor misses, and fixing it would have
    asserted that the United States is MADE OF fifty states. The metric would have risen. This is
    the check that says no."""
    _needs_profile()
    v = judge("made_of", CONSISTING_OF)
    assert v.accept is False
    assert v.familiar < 0.35
    assert any("states" in a for a in v.alien)


def test_genuine_material_objects_are_not_blocked():
    """The opposite failure. A judge that refuses real improvements would stop the loop entirely,
    which is worse than having no judge -- at least a missing gate is visible."""
    _needs_profile()
    v = judge("made_of", MATERIALS)
    assert v.accept is True
    assert v.familiar > 0.8


def test_novel_but_plausible_objects_survive():
    """A real improvement brings objects the relation has NOT seen; that is what makes it an
    improvement. The threshold is deliberately low so novelty passes and only wholesale strangeness
    fails."""
    _needs_profile()
    mixed = ["steel", "wood", "titanium alloy", "recycled plastic", "bamboo fibre", "cotton"]
    assert judge("made_of", mixed).accept is True


def test_the_profile_is_counted_not_declared():
    """Nothing in this module lists what a material is. If it did, it would be the hand-written rule
    the project's doctrine rejects -- and it would not survive a change of corpus."""
    p = profile("made_of")
    if sum(p.values()) < 200:
        pytest.skip("no made_of rows on disk in this environment")
    assert len(p) > 100                                  # a real distribution, not a short list
    assert p.most_common(1)[0][1] > 1                    # counted, with frequencies


def test_a_relation_with_no_history_is_refused_not_waved_through():
    """This test used to assert the OPPOSITE, and it was pinning a defect.

    The old behaviour returned accept=True with "abstaining rather than guessing", which reads
    honest and is not: a relation with no rows cannot be judged against itself, and accepting on
    that basis makes every NEW relation a sink. It bit immediately. The loop added `has_a`, which
    had zero rows, and the next run produced six proposals mapping cues like `intended to` onto it
    -- and judge(has_a, ["nonsense", "garbage"]) returned accept=True in a direct test.

    A new relation now has to be corroborated by the external vocabulary that named it. Where that
    evidence cannot be obtained, the answer is no. Refusing is the safe default; accepting is not."""
    v = judge("has_a", ["nonsense", "garbage", "random words"])
    assert v.accept is False
    assert "no history" in v.reason or "cannot be judged against itself" in v.reason

    unknown = judge("a_relation_that_does_not_exist", ["anything", "at all"])
    assert unknown.accept is False
    assert "nothing can corroborate" in unknown.reason


# ---------------------------------------------------------------- the field failures, pinned
# The first version of this gate passed its own curated acid test and was then defeated at scale by
# the exact case it was written for. These pin the behaviour that survived four rounds of that.

def test_an_ambiguous_cue_is_refused_at_scale():
    """`consisting of` reaches 68% instance agreement -- but for the ACTION cluster, while the
    proposal was made_of. Agreement on the wrong kind is not agreement."""
    _needs_profile()
    from packages.self_repair.relation_fit import coherence
    objs = ["one thousand years", "fifty states", "four constituent countries", "committees",
            "a single word", "representatives of the member states", "two islands", "air"]
    c = coherence(objs)
    v = judge("made_of", objs)
    assert v.accept is False
    assert c["modal_cluster"] is not None


def test_relation_clusters_are_measured_not_declared():
    """used_for and capable_of share 7,384 head nouns (jaccard 0.272) against 0.055 and 0.045 for
    every other pair -- both take actions. Treating their disagreement as ambiguity was wrong, and
    the grouping that fixes it is counted from the profiles, not written down."""
    from packages.self_repair.relation_fit import clusters
    if sum(profile("made_of").values()) < 200:
        pytest.skip("no profiles on disk in this environment")
    groups = clusters()
    verb_cluster = [g for g in groups if "used_for" in g][0]
    assert "capable_of" in verb_cluster
    assert ["made_of"] in groups


# -------------------------------------------------------- within-cluster discrimination
# The gate could tell the verb cluster from made_of and could not tell used_for from capable_of.
# Measured on 15,729 held-out ConceptNet pairs: the last-token signal scored 0.645 against a
# majority-class baseline of 0.729 -- it was WORSE than guessing -- while the first token scored 0.810.

def test_instrumental_and_agentive_objects_separate():
    """cutting/storing/holding are instrumental; fly/bite/breathe are agentive. The nouns they take
    do not separate (jaccard 0.290) and the verbs do (0.136), which is why the head is the FIRST
    token for the action relations and the last for made_of."""
    _needs_profile()
    from packages.self_repair.relation_fit import discriminate
    instrumental = discriminate(["cutting bread", "storing food", "holding water", "opening cans"])
    agentive = discriminate(["fly", "bite people", "breathe air", "swim"])
    assert instrumental["best"] == "used_for"
    assert agentive["best"] == "capable_of"


def test_the_noun_cluster_still_reads_its_head_last():
    """made_of takes materials, and `stainless steel` is steel, not stainless. Fixing the verb
    relations must not break the one that was already right."""
    _needs_profile()
    from packages.self_repair.relation_fit import discriminate
    assert discriminate(["steel", "wood", "plastic", "cotton"])["best"] == "made_of"


def test_clustering_cannot_re_enter_the_relation_aware_head():
    """A cycle I wrote and that hung the process: _head asked whether a relation is verb-taking,
    which asked clusters(), which builds profiles, which call _head. Clustering uses the plain head
    so the cycle is cut at its narrowest point."""
    from packages.self_repair.relation_fit import _head_plain, clusters
    assert _head_plain("stainless steel") == "steel"
    assert clusters(head=_head_plain)                      # completes rather than recursing
