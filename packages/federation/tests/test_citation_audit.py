# -*- coding: utf-8 -*-
"""The reputation loop's properties, pinned — especially the two it must never violate.

A reputation system that leaks into consensus weight destroys the domain-keyed invariant the public
scope rests on, and one that reads "we could not re-extract it" as "the peer lied" punishes honest peers
for our own extractor's blind spots. Both are tested here rather than promised in a docstring.
"""
from __future__ import annotations

from packages.federation.citation_audit import (
    CONFIRMED,
    INCONCLUSIVE,
    REFUTED,
    CitationAuditor,
    PeerLedger,
    detection_odds,
)
from packages.federation.world_facts import WorldFactContribution, merge_into_tally
from packages.knowledge_acquisition.consensus import ConsensusTally


class FakeFetcher:
    """Serves canned pages so the audit is tested without touching the network."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls = []

    def fetch(self, url: str):
        self.calls.append(url)
        if url in self.pages:
            return url, 200, self.pages[url].encode("utf-8")
        return url, 404, b""


def _auditor(pages, url_for=None):
    return CitationAuditor(ledger=PeerLedger(), fetcher=FakeFetcher(pages),
                           url_for=url_for or (lambda d, e: f"https://{d}/wiki/{e}"))


def test_a_true_citation_is_confirmed():
    a = _auditor({"https://en.wiktionary.org/wiki/trowel":
                  "<p>A trowel is a tool used for spreading mortar.</p>"})
    c = WorldFactContribution.from_triples(
        "honest", [("trowel", "used_for", "spreading", ["en.wiktionary.org"])])
    c.sanitize()
    verdict, _why = a.verify(c.facts[0])
    assert verdict == CONFIRMED


def test_a_fabricated_citation_is_refuted():
    """The page loads and the claimed words are simply not on it."""
    a = _auditor({"https://en.wiktionary.org/wiki/trowel":
                  "<p>A trowel is a tool used for spreading mortar.</p>"})
    c = WorldFactContribution.from_triples(
        "liar", [("trowel", "used_for", "interstellar navigation", ["en.wiktionary.org"])])
    c.sanitize()
    verdict, why = a.verify(c.facts[0])
    assert verdict == REFUTED, why


def test_failing_to_reach_the_page_is_never_a_refutation():
    """Our fetch problem must never become the peer's crime."""
    a = _auditor({})                       # every url 404s
    c = WorldFactContribution.from_triples(
        "honest", [("trowel", "used_for", "spreading", ["en.wiktionary.org"])])
    c.sanitize()
    verdict, _why = a.verify(c.facts[0])
    assert verdict == INCONCLUSIVE


def test_extractor_blindness_is_not_refutation():
    """The page says it in prose our extractor cannot parse. That is our limit, not a lie.

    Measured this session: `kiosk` returned 0 sightings from 4 documents whose text described its use.
    Scoring that as a refutation would punish honest peers for our recall."""
    a = _auditor({"https://en.wikipedia.org/wiki/kiosk":
                  "<p>Students use kiosks to look up campus events.</p>"})
    c = WorldFactContribution.from_triples(
        "honest", [("kiosk", "used_for", "look up campus events", ["en.wikipedia.org"])])
    c.sanitize()
    verdict, _why = a.verify(c.facts[0])
    assert verdict == CONFIRMED, "the words ARE on the page; only our extractor missed them"


def test_one_refutation_stops_the_peer_being_read():
    led = PeerLedger()
    assert led.should_read("p") is True, "an unchecked peer is read; the first contribution is sampled"
    led.note("p", REFUTED, "fabricated")
    assert led.should_read("p") is False


def test_inconclusive_checks_never_stop_a_peer():
    led = PeerLedger()
    for _ in range(50):
        led.note("p", INCONCLUSIVE, "robots")
    assert led.should_read("p") is True


def test_reputation_never_changes_what_a_fact_weighs():
    """THE structural rule. A trusted peer and an unknown peer contribute identically to the tally,
    because the tally counts DOMAINS. If reputation could weight a fact, the peer would be back inside
    the consensus arithmetic."""
    led = PeerLedger()
    for _ in range(20):
        led.note("trusted", CONFIRMED, "")
    t_trusted, t_unknown = ConsensusTally(), ConsensusTally()
    for peer, tally in (("trusted", t_trusted), ("brand-new", t_unknown)):
        c = WorldFactContribution.from_triples(
            peer, [("trowel", "used_for", "spreading", ["en.wiktionary.org"])])
        c.sanitize()
        merge_into_tally(tally, c)
    assert t_trusted._ranked() == t_unknown._ranked()


def test_audit_reports_its_own_detection_odds():
    a = _auditor({"https://en.wiktionary.org/wiki/trowel": "spreading"})
    facts = [("trowel", "used_for", "spreading", ["en.wiktionary.org"]) for _ in range(100)]
    c = WorldFactContribution.from_triples("peer", facts)
    c.sanitize()
    out = a.audit(c, sample_rate=0.05)
    assert out["checked"] == 5
    assert 0.0 < out["detection_odds_if_1_poisoned"] < 0.2, out
    assert out["detection_odds_if_10_poisoned"] > out["detection_odds_if_1_poisoned"]
    assert "proof" in out["caveat"]


def test_detection_odds_is_the_stated_formula():
    assert detection_odds(0.0, 10) == 0.0
    assert detection_odds(1.0, 1) == 1.0
    assert abs(detection_odds(0.05, 1) - 0.05) < 1e-9
    assert abs(detection_odds(0.05, 10) - (1 - 0.95 ** 10)) < 1e-9


def test_a_poisoned_peer_is_caught_and_refused():
    a = _auditor({"https://en.wiktionary.org/wiki/trowel":
                  "<p>A trowel is used for spreading mortar.</p>"})
    facts = [("trowel", "used_for", "spreading", ["en.wiktionary.org"])] * 4
    facts.append(("trowel", "used_for", "interstellar navigation", ["en.wiktionary.org"]))
    c = WorldFactContribution.from_triples("liar", facts)
    c.sanitize()
    out = a.audit(c, sample_rate=1.0)
    assert out["refuted"] >= 1, out
    assert out["should_read_now"] is False
