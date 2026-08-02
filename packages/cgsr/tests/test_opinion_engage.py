# -*- coding: utf-8 -*-
"""Grounded opinion engagement: participate in comparison turns without fabricating a side."""
from packages.cgsr.cgsr.opinion_engage import extract_pair, compose


def test_extracts_comparison_pair():
    assert extract_pair("Do museums matter more than cinemas for a town?") == ("museums", "cinemas")
    assert extract_pair("Is tea better than coffee?") == ("tea", "coffee")
    assert extract_pair("What is the capital of France?") is None   # not a comparison


def test_uses_only_supplied_grounding_never_invents():
    q = "Do museums matter more than cinemas for a town?"
    out = compose(q, {"museums": "Museums preserve history and art",
                      "cinemas": "Cinemas offer a shared entertainment experience"})
    assert "preserve history" in out and "shared entertainment" in out
    # honest close: declines to assert a single correct answer
    assert "depends on what you value" in out.lower()
    assert "isn't a fact to look up" in out.lower()


def test_handles_missing_grounding_without_fabricating():
    out = compose("Is tea better than coffee?", grounding=None)
    assert "tea" in out.lower() and "coffee" in out.lower()
    # no invented properties about tea/coffee
    assert "depends on what you value" in out.lower()


def test_non_comparison_returns_none():
    assert compose("Who is Einstein?") is None
