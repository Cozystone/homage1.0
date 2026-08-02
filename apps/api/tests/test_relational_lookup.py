# -*- coding: utf-8 -*-
"""Relational-lookup lane — owner-priority defect fix (2026-07-21).

Guards the regression where "what is the capital of France?" was answered by DEFINING the head
noun ("capital is named after Washington…") at confidence 0.91. The lane now parses the
relational shape, resolves by GRAPH edge, and either answers with a certificate naming the edge
or HONESTLY abstains — it never emits the head-noun define. Genuine defines are untouched.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from packages.base_brain.relational_lookup import parse_relational_shape, resolve_relational
from packages.base_brain.relational_router import RelationalRouter, _HELDOUT_PATH, extract_features

client = TestClient(app)


def _answer(query: str) -> dict:
    resp = client.post("/api/base-brain/answer",
                       json={"query": query, "language": "en", "mode": "default"})
    assert resp.status_code == 200
    return resp.json()


class _FakeStore:
    """Deterministic in-memory store so the resolution logic is tested without the 7M-row
    graph — facts_about returns exactly the edges we hand it."""

    def __init__(self, facts: dict[str, list[tuple[str, str, str]]]) -> None:
        self._f = facts

    def __len__(self) -> int:
        return sum(len(v) for v in self._f.values())

    def facts_about(self, subject: str, limit: int = 60):
        return list(self._f.get(subject, []))[:limit]


# ── ① 'capital of France' no longer yields the head-noun (Washington) define ──────────────────
def test_capital_of_france_is_not_headnoun_define() -> None:
    payload = _answer("what is the capital of France?")
    answer = str(payload["answer"])
    # the exact measured defect string, and the head-noun define shape, must be gone
    assert "named after Washington" not in answer
    assert "capital is named after" not in answer.lower()
    assert payload["trace"]["intent"] == "relational"
    # honest outcome: either the grounded graph answer (Paris) or an explicit abstention —
    # never a confident definition of the word "capital".
    assert ("Paris" in answer) or ("don't hold a grounded" in answer)
    assert payload["local_user_brain_used"] is False
    assert payload["external_llm_used"] is False


def test_other_relational_defects_are_not_headnoun_defines() -> None:
    # population / boiling point: the entity has no such edge in this store -> honest abstention,
    # never a define of "population" / "boiling".
    for query, rel in [("what is the population of France?", "population"),
                        ("what is the boiling point of water?", "boiling point")]:
        payload = _answer(query)
        answer = str(payload["answer"])
        assert payload["trace"]["intent"] == "relational"
        assert "don't hold a grounded" in answer
        assert rel in answer  # names the relation it couldn't ground
        assert payload["confidence"] <= 0.3  # honest low confidence on an abstention

    # possessive form routes the same way
    poss = _answer("France's capital")
    assert poss["trace"]["intent"] == "relational"
    assert "named after Washington" not in str(poss["answer"])


def test_speed_of_light_is_defined_as_the_compound_not_the_head_noun() -> None:
    # "speed of light" is a grounded COMPOUND entity: it must be DEFINED as the compound, never
    # decomposed to the head noun "speed" (the measured "speed has composed many other scores
    # for film…" bug). Needs the graph to know the compound; skip honestly if the store is absent.
    from packages.graph_scale.answer_bridge import _store

    store = _store()
    if store is None or len(store) == 0:
        pytest.skip("graph store unavailable in this environment")
    payload = _answer("what is the speed of light?")
    answer = str(payload["answer"]).lower()
    assert "composed many other scores" not in answer
    assert "for film and television" not in answer
    assert "speed of light" in answer  # the compound is the subject, not "speed"
    assert payload["trace"]["intent"] == "define"


# ── ② genuine defines are unaffected ─────────────────────────────────────────────────────────
def test_genuine_define_photosynthesis_unaffected() -> None:
    payload = _answer("what is photosynthesis?")
    answer = str(payload["answer"]).lower()
    assert "photosynthesis" in answer
    assert payload["trace"]["intent"] != "relational"
    # still the normal base-brain define surface, not a relational/abstain kind
    assert payload["answer_kind"] == "base_brain_zero_user_data"
    assert payload["useful_answer"] is True


def test_plain_shapes_fall_through_the_lane() -> None:
    # non-relational shapes return None from the lane (so the unchanged pipeline handles them)
    assert resolve_relational("what is photosynthesis?", "en") is None
    assert resolve_relational("what is a black hole?", "en") is None
    assert resolve_relational("hello there", "en") is None
    # Korean is refused upstream; the lane declines it too
    assert resolve_relational("프랑스의 수도는?", "en") is None


# ── ③ the learned router classifies a held-out paraphrase set >= 0.9 ─────────────────────────
def test_router_heldout_accuracy_at_least_0_9() -> None:
    if not _HELDOUT_PATH.exists():  # deterministic artifact — regenerate if a fresh tree lacks it
        from packages.base_brain.relational_router import train_and_save
        train_and_save()
    router = RelationalRouter.load()
    rows = [json.loads(line) for line in _HELDOUT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) >= 30, "held-out set should be a few dozen examples"
    correct = 0
    for row in rows:
        cls, _prob = router.classify(row["query"])
        pred = 1 if cls == "relational" else 0
        correct += int(pred == int(row["label"]))
    accuracy = correct / len(rows)
    assert accuracy >= 0.9, f"router held-out accuracy {accuracy:.3f} < 0.9"


def test_router_features_are_regex_only_not_the_label() -> None:
    # the decision reads FEATURES, not any hand rule that peeks at the answer: a relation-word
    # question exposes rel_in_vocab; a plain define does not.
    assert extract_features("what is the capital of France?")["rel_in_vocab"] == 1.0
    assert extract_features("what is photosynthesis?")["rel_in_vocab"] == 0.0
    assert RelationalRouter.load().classify("what is the capital of France?")[0] == "relational"
    assert RelationalRouter.load().classify("what is photosynthesis?")[0] == "define"


# ── ④ the certificate names the edge when the lane ANSWERS ────────────────────────────────────
def test_certificate_names_the_edge_when_answered() -> None:
    # a clean forward edge (light --made_of--> energy, photons) resolves to a grounded answer
    # whose certificate NAMES the edge it used.
    store = _FakeStore({"light": [("light", "is_a", "energy"),
                                  ("light", "made_of", "energy"),
                                  ("light", "made_of", "photons")]})
    result = resolve_relational("what is light made of?", "en", store=store)
    assert result is not None
    assert result["answer_kind"] == "relational_edge_lookup"
    assert result["intent"] == "relational"
    assert "made of" in result["answer"].lower()
    cert = result["reasoning_certificate"]
    assert cert["edge"] == "made_of"
    assert cert["derivation_kind"] == "relational_edge_lookup"
    assert any("made_of" in step["fact"] for step in cert["steps"])
    assert result["relational"]["resolved"] is True
    assert result["confidence"] >= 0.8


def test_capital_resolves_with_certificate_when_the_edge_exists() -> None:
    # exactly the defect shape, but with the edge present: the answer is Paris and the
    # certificate names the 'capital' edge (proves the answering path, not just abstention).
    store = _FakeStore({"France": [("France", "is_a", "Country"),
                                   ("France", "capital", "Paris")]})
    result = resolve_relational("what is the capital of France?", "en", store=store)
    assert result is not None
    assert "Paris" in result["answer"]
    assert "named after Washington" not in result["answer"]
    assert result["reasoning_certificate"]["edge"] == "capital"
    assert result["intent"] == "relational"


def test_honest_abstention_when_entity_lacks_the_edge() -> None:
    # entity present, asked edge absent -> honest abstention, never a head-noun define
    store = _FakeStore({"France": [("France", "is_a", "Country")]})
    result = resolve_relational("what is the capital of France?", "en", store=store)
    assert result is not None
    assert result["answer_kind"] == "honest_abstain_relational"
    assert "don't hold a grounded capital fact for France" in result["answer"]
    assert result["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False


def test_parse_relational_shape_variants() -> None:
    assert parse_relational_shape("what is the capital of France?")["entity"] == "France"
    assert parse_relational_shape("what is the capital of France?")["rel_norm"] == "capital"
    assert parse_relational_shape("France's capital")["kind"] == "possessive"
    assert parse_relational_shape("who wrote Hamlet?")["entity"] == "Hamlet"
    assert parse_relational_shape("what is light made of?")["kind"] == "verb"
    assert parse_relational_shape("what is photosynthesis?") is None
