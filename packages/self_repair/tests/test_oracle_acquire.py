# -*- coding: utf-8 -*-
"""Acquiring the arbiter's evidence — and the two things that make it evidence rather than an echo.

Network is not required: the circularity guard and the consensus arithmetic are the parts that must
hold, and both are testable offline.
"""
from __future__ import annotations

from packages.self_repair.oracle_acquire import _trusted_patterns, acquire_for


def test_the_disputed_cue_is_removed_before_mining():
    """The whole reason this is not circular. If the cue under dispute mines the pages that are meant
    to settle it, 2-domain consensus confirms a systematic error instead of a fact -- consensus checks
    whether a FACT is reliably reported, never whether our RELATION assignment is right."""
    kept, dropped = _trusted_patterns("able to")
    assert dropped, "the disputed cue must actually be excluded"
    assert all("able" not in rx.pattern.lower() or "\s+to" not in rx.pattern.lower()
               for _p, rx in kept)


def test_an_unfindable_cue_refuses_rather_than_mining_anyway():
    """If the cue cannot be located in the pattern table, it cannot be excluded, and mining would be
    silently circular. The safe answer is no."""
    r = acquire_for("anything", "used_for", excluding_cue="a cue that is not in the table at all")
    assert r["acquired"] == []
    assert "Refusing" in (r.get("error") or "")


def test_nothing_is_kept_below_the_consensus_floor():
    """One domain saying something is a sighting, not a fact. The floor is the point of going to the
    web at all -- otherwise this would just be a slower way to believe one page."""
    from packages.knowledge_acquisition.consensus import ConsensusTally
    t = ConsensusTally(min_domains=2)
    t.add("navigation", "https://a.com/x")
    t.add("navigation", "https://b.org/y")
    t.add("lonely claim", "https://a.com/z")
    ranked = dict(t._ranked())
    assert ranked["navigation"] >= 2
    assert ranked["lonely claim"] < 2


def test_the_ranked_shape_is_counts_not_sets():
    """Pinned because getting it wrong cost a silent zero. `_ranked()` yields (object, N_DOMAINS) as
    an INT; the first version called len() on it, a bare except swallowed the TypeError, and every
    acquisition returned zero corroborated facts -- which I nearly reported as the gate working."""
    from packages.knowledge_acquisition.consensus import ConsensusTally
    t = ConsensusTally(min_domains=2)
    t.add("x", "https://a.com/1")
    for _obj, n in t._ranked():
        assert isinstance(n, int)
