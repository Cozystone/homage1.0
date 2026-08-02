# -*- coding: utf-8 -*-
"""The honest ceiling: autonomous-now vs needs-a-verifier vs operator-gated-forever."""
from __future__ import annotations

from packages.self_evolution import build_weakness_map, ceiling


def test_partition_has_the_four_honest_buckets():
    part = ceiling.partition(build_weakness_map())
    assert "autonomous_now" in part
    assert "needs_verifier_first" in part
    ogf = part["operator_gated_forever"]
    assert "architecture" in ogf
    assert "immutable_constitution" in ogf


def test_buckets_are_disjoint_and_cover_every_domain():
    wm = build_weakness_map()
    part = ceiling.partition(wm)
    auto = set(part["autonomous_now"])
    needs = {x["domain"] for x in part["needs_verifier_first"]}
    arch = {x["domain"] for x in part["operator_gated_forever"]["architecture"]}
    # every sensed domain lands in exactly one of the three domain buckets
    all_domains = {w.domain for w in wm}
    assert auto | needs | arch == all_domains
    assert auto.isdisjoint(needs)
    assert auto.isdisjoint(arch)
    assert needs.isdisjoint(arch)


def test_a_domain_needing_a_verifier_is_not_in_autonomous_bucket():
    wm = build_weakness_map()
    part = ceiling.partition(wm)
    for w in wm:
        if not w.verifier_exists:
            assert w.domain not in part["autonomous_now"], w.domain
            assert w.domain in {x["domain"] for x in part["needs_verifier_first"]}


def test_immutable_bucket_names_the_moral_core_and_tests():
    part = ceiling.partition(build_weakness_map())
    immut = part["operator_gated_forever"]["immutable_constitution"]
    joined = " ".join(immut["protected_examples"]).lower()
    assert "moral_invariants" in joined
    assert "test" in joined
    assert "verifier coverage" in part["principle"].lower()


def test_render_is_nonempty_and_mentions_verifier():
    text = ceiling.render(build_weakness_map())
    assert "autonomously evolvable now" in text
    assert "needs a verifier" in text
