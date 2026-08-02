# -*- coding: utf-8 -*-
"""A1a: learn WHAT a merged name refers to, from sources, with corroboration.

A wrong referent is worse than a missing one: it attracts edges that then look placed. So the same
k-source discipline the acquisition loop applies to values is applied here to identity.
"""
from __future__ import annotations

from packages.knowledge_repair.disambiguation import (
    acquire_referents, disambiguation_query, propose_referents)

PAGE_A = ("https://a.example/athens", """
Athens (Greece) is the capital and largest city of Greece.
Athens (Ohio) is a city in the United States.
Athens, Georgia is a consolidated city-county in the United States.
""")
PAGE_B = ("https://b.example/athens", """
Athens (Greece) - the ancient Greek city
Athens (Ohio) - home of Ohio University
Athens (Ontario) - a township in Canada
""")
PAGE_C = ("https://c.example/unrelated", "Nothing about that name appears in this document.")


def test_referents_stated_by_two_sources_are_proposed():
    props = propose_referents("Athens", [PAGE_A, PAGE_B])
    keys = {p.key for p in props}
    assert "Athens (Greece)" in keys and "Athens (Ohio)" in keys


def test_a_referent_only_one_source_states_is_not_proposed():
    """One page asserting a referent is a claim; two independent ones are evidence."""
    props = propose_referents("Athens", [PAGE_A, PAGE_B])
    keys = {p.key for p in props}
    assert "Athens (Ontario)" not in keys       # only PAGE_B
    assert "Athens (Georgia)" not in keys       # only PAGE_A


def test_markers_come_from_the_qualifier_the_source_stated():
    """The markers are extracted, never guessed -- they are what `attribution` then matches on."""
    (greece,) = [p for p in propose_referents("Athens", [PAGE_A, PAGE_B])
                 if p.key == "Athens (Greece)"]
    assert "Greece" in greece.markers
    assert greece.as_referent().key == "Athens (Greece)"


def test_corroboration_orders_the_proposals():
    props = propose_referents("Athens", [PAGE_A, PAGE_B])
    assert props[0].corroboration >= props[-1].corroboration


def test_a_document_not_mentioning_the_name_contributes_nothing():
    assert propose_referents("Athens", [PAGE_C]) == []


def test_lowering_corroboration_is_an_explicit_choice_not_a_default():
    """Available for a single-source probe, but the default stays 2 so identity is never asserted
    on one page."""
    keys = {p.key for p in propose_referents("Athens", [PAGE_A], min_corroboration=1)}
    assert "Athens (Georgia)" in keys


def test_the_query_does_not_presuppose_how_many_referents_exist():
    q = disambiguation_query("Athens")
    assert "Athens" in q
    assert not any(d in q for d in ("two", "three", "five"))


def test_a_source_failure_yields_no_proposal_rather_than_a_guess():
    """Keeping the node merged is the correct outcome when nothing could be learned."""
    class _Broken:
        def documents(self, *a, **k):
            raise RuntimeError("network down")
    assert acquire_referents("Athens", _Broken()) == []


def test_acquire_uses_the_evidence_source_it_is_given():
    seen = {}

    class _Fake:
        def documents(self, entity, rel_norm, query=""):
            seen.update(entity=entity, rel_norm=rel_norm, query=query)
            return [PAGE_A, PAGE_B]

    props = acquire_referents("Athens", _Fake())
    assert seen["entity"] == "Athens" and "Athens" in seen["query"]
    assert {p.key for p in props} >= {"Athens (Greece)", "Athens (Ohio)"}
