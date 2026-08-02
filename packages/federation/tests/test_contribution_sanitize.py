# -*- coding: utf-8 -*-
"""Structure-not-data + privacy gate (constitution 1 + 4).

A contribution federates the SHAPE of an ability — never a corpus, a lived record, a personal graph,
or any PII/entity. These tests pin that a data-carrying payload is rejected, that PII/entity/harm are
rejected (wild_web reuse), and — critically — that legitimate NUMERIC organ-params PASS (a weight
vector is structure, not identity).
"""
from __future__ import annotations

from packages.federation.contribution import Contribution, sanitize


# ── clean structure passes ─────────────────────────────────────────────────────────────────────────
def test_clean_schema_is_structure_and_passes():
    payload = {
        "rules": [
            {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
            {"on": "move", "args": ["e", "src", "dst"],
             "effect": [["clear", "at", "e"], ["set", "at", "e", "dst"]]},
        ],
        "queries": {"where": {"predicate": "at", "by": "e"}},
    }
    res = sanitize(payload)
    assert res.ok is True, res.reasons
    assert res.reasons == []


def test_numeric_organ_params_are_structure_and_pass():
    """A weight vector + bias is STRUCTURE (the shape of a decision boundary), not data — it must pass
    even though it is 'content'. This is what separates a param from a lived record."""
    payload = {"weights": [0.31, -0.5, 1.2, -0.08], "bias": -0.2, "feature_dim": 4}
    res = sanitize(payload)
    assert res.ok is True, res.reasons


def test_router_diff_of_lane_rules_passes():
    payload = {"routes": {"define|term": "define", "attr|of": "relational"}, "default": "unknown"}
    assert sanitize(payload).ok is True


# ── data-carrying payloads are rejected ─────────────────────────────────────────────────────────────
def test_corpus_carrying_key_is_rejected():
    """A payload shaped like a CORPUS / lived record is data, not structure — rejected by shape."""
    for key in ("corpus", "facts", "lived_record", "memories", "personal_graph", "transcript", "text"):
        res = sanitize({key: ["some", "content", "rows"]})
        assert res.ok is False, key
        assert "data_carrying_key" in res.reasons, (key, res.reasons)


def test_ground_facts_nested_are_rejected():
    payload = {"rules": [], "triples": [{"s": "a", "p": "b", "o": "c"}]}
    res = sanitize(payload)
    assert res.ok is False
    assert "data_carrying_key" in res.reasons


# ── privacy gates (wild_web reuse) ──────────────────────────────────────────────────────────────────
def test_pii_email_is_rejected():
    res = sanitize({"rules": [], "note": "learned from alice@example.com"})
    assert res.ok is False
    assert "pii" in res.reasons


def test_entity_leak_proper_noun_is_rejected():
    """A surviving proper noun / place / URL is an identity leak (wild_web anonymizer)."""
    res = sanitize({"rules": [], "note": "distilled from a chat with Sarah Kim in Seoul"})
    assert res.ok is False
    assert "entity_leak" in res.reasons


def test_harmful_content_is_rejected():
    res = sanitize({"rules": [], "note": "how to make a bomb and attack a school"})
    assert res.ok is False
    assert "harmful" in res.reasons


def test_prose_smuggled_as_a_value_is_rejected():
    """An over-long string is prose (smuggled data), not a structure token — rejected even without a
    proper noun."""
    long_text = "this is a long free-form paragraph of lived content " * 6
    res = sanitize({"rules": [], "blob": long_text})
    assert res.ok is False
    assert "prose" in res.reasons


def test_empty_payload_is_rejected():
    assert sanitize({}).ok is False
    assert "empty" in sanitize({}).reasons


# ── Contribution.sanitize() wiring ──────────────────────────────────────────────────────────────────
def test_contribution_sanitize_flags_pii_node_id():
    c = Contribution(node_id="contact-me@evil.com", capability_kind="schema",
                     capability_id="x", payload={"rules": []}, target_suite="location_tracking")
    res = c.sanitize()
    assert res.ok is False
    assert "pii_node_id" in res.reasons


def test_contribution_digest_is_stable_and_ignores_self_report():
    a = Contribution(node_id="n", capability_kind="schema", capability_id="x",
                     payload={"rules": [1]}, self_reported_score=0.1, target_suite="s")
    b = Contribution(node_id="n", capability_kind="schema", capability_id="x",
                     payload={"rules": [1]}, self_reported_score=0.99, target_suite="s")
    assert a.digest() == b.digest()          # self-report is a claim, not part of the capability
