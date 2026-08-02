# -*- coding: utf-8 -*-
"""The public scope's safety properties, pinned. These are the reasons the amendment is safe.

The constitution of 2026-07-22 kept crawled facts out of federation entirely. The owner authorised a
public scope on 2026-07-31, and a scope that can be argued about in prose is not a scope. Every
guarantee the amendment rests on is a test here, so a future change that breaks one fails loudly
instead of quietly turning federation into a laundering channel.
"""
from __future__ import annotations

import pytest

from packages.federation.world_facts import (
    PERSONAL_PREDICATES,
    WorldFactContribution,
    merge_into_tally,
    peer_flood_check,
)
from packages.knowledge_acquisition.consensus import ConsensusTally

FACT = ("trowel", "used_for", "spreading", ["en.wiktionary.org"])


def test_a_peer_can_never_become_a_source():
    """THE invariant. Twenty peers citing one domain is one domain, so a ring cannot manufacture
    consensus and a compromised node cannot promote its inventions by repetition."""
    out = peer_flood_check(ConsensusTally, FACT, n_peers=20)
    assert out["distinct_domains"] == 1, out
    assert not out["reached_floor"], out
    assert out["safe"], out


def test_two_peers_citing_two_different_domains_do_reach_the_floor():
    """The other half: real independent sourcing must still work, or the lane is useless."""
    tally = ConsensusTally()
    for i, dom in enumerate(("en.wiktionary.org", "gcide.gnu.org.ua")):
        c = WorldFactContribution.from_triples(f"peer-{i}", [("trowel", "used_for", "spreading",
                                                              [dom])])
        c.sanitize()
        merge_into_tally(tally, c)
    verdict = tally.resolve()
    assert verdict is not None and verdict.corroborated, "independent domains must corroborate"
    assert verdict.n_domains == 2


def test_a_fact_without_provenance_never_travels():
    """A fact that cannot say who asserts it is indistinguishable from an invention."""
    c = WorldFactContribution.from_triples("peer", [("trowel", "used_for", "spreading", [])])
    rep = c.sanitize()
    assert rep.kept == 0
    assert rep.dropped.get("no_provenance") == 1


def test_personal_predicates_are_refused_in_the_public_lane():
    """Constitution layer 3 is untouched: the lived record never merges, however it is labelled."""
    triples = [("atanor", p, "something", ["example.org"]) for p in sorted(PERSONAL_PREDICATES)[:6]]
    c = WorldFactContribution.from_triples("peer", triples)
    rep = c.sanitize()
    assert rep.kept == 0, rep.sample_dropped
    assert rep.dropped.get("personal_predicate") == len(triples)


def test_prefixed_personal_predicates_are_refused_too():
    """`felt_valence` is the lived record wearing a suffix."""
    c = WorldFactContribution.from_triples("peer", [("atanor", "felt_valence", "0.7",
                                                     ["example.org"])])
    assert c.sanitize().dropped.get("personal_predicate") == 1


def test_pii_bearing_facts_are_refused():
    c = WorldFactContribution.from_triples(
        "peer", [("contact", "used_for", "call 010-1234-5678 or a@b.com", ["example.org"])])
    rep = c.sanitize()
    assert rep.kept == 0
    assert rep.dropped.get("pii_or_harm") == 1


def test_the_capability_lane_still_rejects_facts():
    """The amendment opened ONE named lane. The structure-only lane must be unchanged."""
    from packages.federation.crawl_capability import reject_reason_for_facts

    out = reject_reason_for_facts()
    assert out["ok"] is False
    assert "data_carrying_key" in out["reasons"]


def test_urls_are_accepted_as_provenance_and_reduced_to_domains():
    """A peer may cite a url; what the tally counts is the domain, so two pages of one site are one."""
    c = WorldFactContribution.from_triples(
        "peer", [("trowel", "used_for", "spreading",
                  ["https://en.wiktionary.org/wiki/trowel", "https://en.wiktionary.org/wiki/spread"])])
    c.sanitize()
    assert c.facts[0].source_domains == ("en.wiktionary.org",)
    tally = ConsensusTally()
    merge_into_tally(tally, c)
    verdict = tally.resolve()
    assert verdict is None or not verdict.corroborated, "one site is one source"


def test_digest_is_stable_and_content_addressed():
    a = WorldFactContribution.from_triples("peer-a", [FACT])
    b = WorldFactContribution.from_triples("peer-b", [FACT])
    assert a.digest() == b.digest(), "the same facts have the same digest whoever sent them"


def test_round_trip_survives_serialisation():
    a = WorldFactContribution.from_triples("peer", [FACT])
    a.sanitize()
    b = WorldFactContribution.from_dict(a.as_dict())
    assert [f.as_dict() for f in b.facts] == [f.as_dict() for f in a.facts]


@pytest.mark.parametrize("n_peers", [2, 5, 50])
def test_flood_is_safe_at_every_size(n_peers):
    out = peer_flood_check(ConsensusTally, FACT, n_peers=n_peers)
    assert out["distinct_domains"] == 1
    assert not out["reached_floor"]
