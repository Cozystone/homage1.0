# -*- coding: utf-8 -*-
"""Generative particle synthesis — unlimited, grounded, reproducible."""

from __future__ import annotations

from packages.splatra_imagination.generative import (
    concept_signature, form_descriptor, synthesize_form,
)


def test_different_concepts_yield_different_forms():
    a = form_descriptor("물")
    b = form_descriptor("쿠버네티스")
    c = form_descriptor("사랑")
    # not a fixed vocabulary: distinct signatures AND distinct geometry params
    assert a["signature"] != b["signature"] != c["signature"]
    assert len({a["primary_lobes"], b["primary_lobes"], c["primary_lobes"]}) >= 2


def test_same_concept_is_reproducible():
    a = synthesize_form("블랙홀", count=600)
    b = synthesize_form("블랙홀", count=600)
    assert len(a) == len(b)
    assert all(abs(p1.x - p2.x) < 1e-9 and abs(p1.y - p2.y) < 1e-9 for p1, p2 in zip(a, b))


def test_graph_grounding_shifts_complexity():
    # a concept with a richer knowledge neighbourhood gets a more complex form
    poor = form_descriptor("X", {"degree": 2, "relation_types": 1})
    rich = form_descriptor("X", {"degree": 35, "relation_types": 9})
    assert rich["complexity"] > poor["complexity"]
    assert rich["grounded"] is True


def test_particles_bounded_and_in_box():
    ps = synthesize_form("나무", count=5000)
    assert 200 <= len(ps) <= 6000
    assert all(-1.95 <= p.x <= 1.95 and -1.95 <= p.y <= 1.95 and -1.95 <= p.z <= 1.95 for p in ps)
    # animated: at least some particles carry velocity
    assert any(abs(p.vx) + abs(p.vy) + abs(p.vz) > 0 for p in ps)


def test_signature_is_stable_and_bounded():
    s1 = concept_signature("양자역학")
    s2 = concept_signature("양자역학")
    assert s1 == s2 and len(s1) == 8
    assert all(0.0 <= v <= 1.0 for v in s1)
