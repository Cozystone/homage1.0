# -*- coding: utf-8 -*-
"""Gate (Switch 2 v0): retrieval PROPOSES the recorded module for a near-duplicate failure and
ABSTAINS honestly (proposal=None) for a novel family. The generative path is a frontier stub."""
import random

import pytest

from packages.meta_diagnosis.recipe_ledger import add_recipe
from packages.meta_diagnosis.failure_signature import failure_signature
from packages.meta_diagnosis.meta_diagnose import diagnose, propose_novel_module, NOVEL_REASON
from packages.meta_diagnosis.tests.synthetic_families import colour_only_task, object_removal_task


def _seed_family_a_recipe(path, rng):
    add_recipe(
        failure_signature=failure_signature(colour_only_task(rng)[0]),
        cluster_label="colour-only", module_name="recolor_relational_v1",
        module_desc="recolour keyed on object relation",
        lift_before=0.10, lift_after=0.50, task_ids_fixed=["a_seed"],
        notes="", ts="2026-07-23T00:00:00Z", path=path,
    )


def test_near_duplicate_retrieves_recorded_module(tmp_path):
    p = tmp_path / "recipes.json"
    rng = random.Random(5)
    _seed_family_a_recipe(p, rng)

    # a NEW family-A failure (different cells/colours, same structure) -> retrieves A's module
    new_a = failure_signature(colour_only_task(rng)[0])
    d = diagnose(new_a, path=p)
    assert d["proposal"] is not None
    assert d["proposal"]["module_name"] == "recolor_relational_v1"
    assert d["proposal"]["cluster_label"] == "colour-only"
    assert d["best_similarity"] >= 0.75
    assert d["proposal"]["confidence"] >= 0.75


def test_novel_family_abstains_no_fabrication(tmp_path):
    p = tmp_path / "recipes.json"
    rng = random.Random(6)
    _seed_family_a_recipe(p, rng)                     # ledger knows ONLY family A

    novel_c = failure_signature(object_removal_task(rng)[0])
    d = diagnose(novel_c, path=p)
    assert d["proposal"] is None                     # never invents a module name
    assert d["reason"] == NOVEL_REASON
    assert d["best_similarity"] < 0.75


def test_empty_ledger_abstains(tmp_path):
    rng = random.Random(1)
    sig = failure_signature(colour_only_task(rng)[0])
    d = diagnose(sig, path=tmp_path / "empty.json")
    assert d["proposal"] is None and d["reason"] == NOVEL_REASON
    assert d["best_similarity"] == 0.0


def test_generative_path_is_frontier_stub():
    rng = random.Random(1)
    sig = failure_signature(colour_only_task(rng)[0])
    with pytest.raises(NotImplementedError):
        propose_novel_module(sig, cluster_descriptor="relational-suspected")
