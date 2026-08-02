# -*- coding: utf-8 -*-
"""Scene-lane wiring inside answer_with_base_brain (2026-07-28).

Control-flow only -- packages/scene_model/tests already covers the algebra and composition
against a fixture, and self_model_calibration.py covers the real 115M-row graph. What THIS file
must prove is the wiring contract:

  * the scene lane is reached only when the relational lane found no shape at all (never competes
    with a working answer -- regression-proof by construction, not by re-testing every shape);
  * an honest scene abstention still short-circuits the define lane (else the head-noun-define
    defect this whole line of work exists to kill would resurface for the shapes the OLD lane
    could not parse);
  * the operator kill-switch actually removes the lane rather than merely disabling its answer.
"""
from __future__ import annotations

import packages.base_brain.zero_user_answer as zua


def _no_relational_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        "packages.base_brain.relational_lookup.resolve_relational", lambda q, language="en": None)


def _refuse_if_called(monkeypatch, target: str) -> None:
    def _boom(*a, **k):
        raise AssertionError(f"{target} must not be called here")
    monkeypatch.setattr(target, _boom)


def test_scene_answer_short_circuits_with_the_relational_contract_shape(monkeypatch):
    _no_relational_shape(monkeypatch)
    monkeypatch.setattr(
        "packages.scene_model.answer_bridge.scene_relational_answer",
        lambda q, language="en": {
            "answer": "3 of the 5 organs I know have no tests.",
            "reasoning_certificate": {"derivation_kind": "scene_evaluation"},
            "confidence": 0.7, "answer_kind": "scene_algebra", "intent": "relational",
            "relational": {"rel": "has_a", "entity": "atanor_organ", "edge": "has_a",
                           "resolved": True},
        })
    out = zua.answer_with_base_brain("which atanor organs have no tests?", language="en")
    assert out["answer"] == "3 of the 5 organs I know have no tests."
    assert out["answer_kind"] == "scene_algebra"
    assert out["useful_answer"] is True
    assert out["trace"]["useful_answer"] is True


def test_scene_abstention_is_useful_false_and_still_short_circuits(monkeypatch):
    """The important one: without this branch, an unresolved scene falls through to the define
    lane and risks the exact 'capital is named after Washington' head-noun defect."""
    _no_relational_shape(monkeypatch)
    monkeypatch.setattr(
        "packages.scene_model.answer_bridge.scene_relational_answer",
        lambda q, language="en": {
            "answer": "I don't hold enough about glorbnak to answer that.",
            "reasoning_certificate": {"derivation_kind": "scene_abstention"},
            "confidence": 0.2, "answer_kind": "scene_algebra_abstain", "intent": "relational",
            "relational": {"rel": None, "entity": "glorbnak", "edge": None, "resolved": False},
        })
    _refuse_if_called(monkeypatch, "packages.base_brain.zero_user_answer.get_semantic_context")
    out = zua.answer_with_base_brain("which glorbnaks have no snurfle?", language="en")
    assert out["useful_answer"] is False
    assert out["answer_kind"] == "scene_algebra_abstain"
    assert "glorbnak" in out["answer"]


def test_a_working_relational_answer_never_reaches_the_scene_lane(monkeypatch):
    """Regression proof by construction: the scene lane cannot alter a shape the old lane already
    resolves, because it is never even called for one."""
    monkeypatch.setattr(
        "packages.base_brain.relational_lookup.resolve_relational",
        lambda q, language="en": {
            "answer": "Capital of france is a paris.",
            "reasoning_certificate": {}, "confidence": 0.9,
            "answer_kind": "relational_edge_lookup", "intent": "relational",
            "relational": {"rel": "capital", "entity": "France", "edge": "capital",
                           "resolved": True},
        })
    _refuse_if_called(monkeypatch, "packages.scene_model.answer_bridge.scene_relational_answer")
    out = zua.answer_with_base_brain("what is the capital of France?", language="en")
    assert out["answer"] == "Capital of france is a paris."
    assert out["answer_kind"] == "relational_edge_lookup"


def test_kill_switch_removes_the_lane_entirely(monkeypatch):
    monkeypatch.setenv("ATANOR_SCENE_LANE", "0")
    _no_relational_shape(monkeypatch)
    _refuse_if_called(monkeypatch, "packages.scene_model.answer_bridge.scene_relational_answer")
    # must not raise -- proves the import/call is skipped, not merely its result discarded
    zua.answer_with_base_brain("which glorbnaks have no snurfle?", language="en")
