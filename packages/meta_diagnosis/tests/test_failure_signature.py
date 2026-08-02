# -*- coding: utf-8 -*-
"""Gate (Switch 1 a-c): FHRR failure-signatures of two synthetic families cluster into TWO groups
with correct membership; and the fixed-vocabulary characterization returns the right descriptor."""
import random

from packages.meta_diagnosis.failure_signature import (
    delta_features, failure_signature, cluster_signatures, characterize_cluster, DESCRIPTOR_VOCAB,
)
from packages.meta_diagnosis.tests.synthetic_families import colour_only_task, object_removal_task
from packages.vsa_reasoning.fhrr_core import resonance


def test_within_family_resonates_between_family_separates():
    rng = random.Random(3)
    a1 = failure_signature(colour_only_task(rng)[0])
    a2 = failure_signature(colour_only_task(rng)[0])
    c1 = failure_signature(object_removal_task(rng)[0])
    c2 = failure_signature(object_removal_task(rng)[0])
    # same structural family -> ~identical signatures
    assert resonance(a1, a2) > 0.95
    assert resonance(c1, c2) > 0.95
    # different families -> clearly below the clustering threshold
    assert resonance(a1, c1) < 0.75


def test_two_families_cluster_into_two_with_correct_membership():
    rng = random.Random(7)
    tasks = {}
    for i in range(4):
        tasks[f"A{i}"] = colour_only_task(rng)
    for i in range(4):
        tasks[f"C{i}"] = object_removal_task(rng)
    ids = list(tasks)
    sigs = [failure_signature(tasks[t][0]) for t in ids]

    result = cluster_signatures(sigs, ids, threshold=0.75)
    clusters = result["clusters"]
    assert len(clusters) == 2

    member_sets = [set(c["member_task_ids"]) for c in clusters]
    assert {"A0", "A1", "A2", "A3"} in member_sets
    assert {"C0", "C1", "C2", "C3"} in member_sets
    # sizes reported correctly
    assert sorted(c["size"] for c in clusters) == [4, 4]


def test_characterize_colour_only_family_returns_colour_only():
    rng = random.Random(11)
    feats = [delta_features(colour_only_task(rng)[0]) for _ in range(4)]
    assert characterize_cluster(feats) == "colour-only"


def test_characterize_object_removal_family_returns_count_change():
    rng = random.Random(12)
    feats = [delta_features(object_removal_task(rng)[0]) for _ in range(4)]
    assert characterize_cluster(feats) == "count-change"


def test_descriptor_always_in_fixed_vocabulary():
    rng = random.Random(13)
    for gen in (colour_only_task, object_removal_task):
        d = characterize_cluster([delta_features(gen(rng)[0]) for _ in range(3)])
        assert d in DESCRIPTOR_VOCAB


def test_delta_features_are_the_expected_structural_deltas():
    rng = random.Random(99)
    fa = delta_features(colour_only_task(rng)[0])
    assert fa["shape_preserved"] and fa["colour_only"]
    assert fa["fg_delta_sign"] == "zero" and fa["obj_delta_sign"] == "zero"

    fc = delta_features(object_removal_task(rng)[0])
    assert fc["shape_preserved"] and not fc["colour_only"]
    assert fc["fg_delta_sign"] == "neg" and fc["obj_delta_sign"] == "neg"
