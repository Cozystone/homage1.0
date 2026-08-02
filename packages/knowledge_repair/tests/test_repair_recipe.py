# -*- coding: utf-8 -*-
"""Registering a repair is only worth anything if a LATER, different failure retrieves it.

The test that matters is not "the recipe was written" -- it is "a merged node the ledger has never
seen matches the recipe, and an unrelated failure does not".
"""
from __future__ import annotations

import numpy as np

from packages.knowledge_repair.repair_recipe import (
    REPAIR_ROLES, register, repair_features, repair_signature)
from packages.meta_diagnosis.recipe_ledger import all_recipes, recipe_signature
from packages.vsa_reasoning.fhrr_core import resonance

ATHENS = repair_features(defect_kind="merged_referent", functional=True, n_values=5,
                         evidence_in_graph=False, residue_trend="falling")


def _register(tmp_path):
    return register(features=ATHENS, module_name="knowledge_repair.purification",
                    module_desc="attribute placeable edges, question the residue, re-measure",
                    coverage_before=0.0, coverage_after=0.129, subjects_fixed=["Athens"],
                    notes="147-edge merged node", ts="2026-07-28T00:00:00",
                    path=tmp_path / "recipes.json")


def test_a_repair_is_stored_with_the_coverage_it_actually_moved(tmp_path):
    rec = _register(tmp_path)
    assert rec["module_name"] == "knowledge_repair.purification"
    assert rec["lift_before"] == 0.0 and rec["lift_after"] == 0.129
    assert all_recipes(tmp_path / "recipes.json")[0]["cluster_label"] == "merged_referent"


def test_an_unseen_merged_node_retrieves_the_recipe(tmp_path):
    """`Cambridge` is a different subject with a different value count, and must still match --
    that is what makes the ledger a flywheel rather than a log."""
    _register(tmp_path)
    stored = recipe_signature(all_recipes(tmp_path / "recipes.json")[0])
    cambridge = repair_signature(repair_features(
        defect_kind="merged_referent", functional=True, n_values=10,
        evidence_in_graph=False, residue_trend="falling"))
    # 10 values buckets to "many" vs Athens' "few": 4 of 5 roles agree.
    assert resonance(stored, cambridge) >= 0.75


def test_an_unrelated_failure_does_not_match(tmp_path):
    """Retrieval has to discriminate, or every failure would 'match' and the proposal is noise."""
    _register(tmp_path)
    stored = recipe_signature(all_recipes(tmp_path / "recipes.json")[0])
    other = repair_signature(repair_features(
        defect_kind="missing_relation", functional=False, n_values=1,
        evidence_in_graph=True, residue_trend="stalled"))
    assert resonance(stored, other) < 0.4


def test_conflict_degree_is_bucketed_so_a_family_can_form(tmp_path):
    """Exact counts would make every node its own family and the ledger would never match."""
    five = repair_signature(repair_features(defect_kind="merged_referent", functional=True,
                                            n_values=5, evidence_in_graph=False))
    six = repair_signature(repair_features(defect_kind="merged_referent", functional=True,
                                           n_values=6, evidence_in_graph=False))
    assert resonance(five, six) > 0.99                      # same family


def test_the_signature_lives_in_the_same_space_as_arc_failures():
    """One ledger serving both domains is the point -- a second space would mean a second copy of
    the algebra, which is the duplication this replaced."""
    from packages.meta_diagnosis.failure_signature import encode_features
    direct = encode_features(ATHENS, REPAIR_ROLES)
    assert np.allclose(direct, repair_signature(ATHENS))
