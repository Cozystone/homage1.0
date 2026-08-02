# -*- coding: utf-8 -*-
"""Gate: recipe ledger round-trip — add 2 recipes, reload from disk, fields intact (incl. the
serialized FHRR signature reconstructing faithfully), and query_by_module filters correctly."""
import random

from packages.meta_diagnosis import recipe_ledger as RL
from packages.meta_diagnosis.failure_signature import failure_signature
from packages.meta_diagnosis.tests.synthetic_families import colour_only_task, object_removal_task
from packages.vsa_reasoning.fhrr_core import resonance


def test_add_two_reload_fields_intact(tmp_path):
    p = tmp_path / "recipes.json"
    rng = random.Random(1)
    sigA = failure_signature(colour_only_task(rng)[0])
    sigC = failure_signature(object_removal_task(rng)[0])

    RL.add_recipe(
        failure_signature=sigA, cluster_label="colour-only",
        module_name="recolor_relational_v1", module_desc="recolour keyed on object relation",
        lift_before=0.10, lift_after=0.42, task_ids_fixed=["a1", "a2"],
        notes="family A seed", ts="2026-07-23T00:00:00Z", path=p,
    )
    RL.add_recipe(
        failure_signature=sigC, cluster_label="count-change",
        module_name="object_remove_v1", module_desc="erase the flagged object",
        lift_before=0.05, lift_after=0.30, task_ids_fixed=["c1"],
        notes="family C seed", ts="2026-07-23T00:05:00Z", path=p,
    )

    got = RL.all_recipes(path=p)                      # reload FROM DISK
    assert len(got) == 2

    a = got[0]
    assert a["cluster_label"] == "colour-only"
    assert a["module_name"] == "recolor_relational_v1"
    assert a["module_desc"] == "recolour keyed on object relation"
    assert a["lift_before"] == 0.10 and a["lift_after"] == 0.42
    assert a["task_ids_fixed"] == ["a1", "a2"]
    assert a["notes"] == "family A seed"
    assert a["ts"] == "2026-07-23T00:00:00Z"

    # the serialized float vector reconstructs to the original complex signature
    assert resonance(RL.recipe_signature(a), sigA) > 0.999
    assert resonance(RL.recipe_signature(got[1]), sigC) > 0.999


def test_query_by_module(tmp_path):
    p = tmp_path / "recipes.json"
    rng = random.Random(2)
    RL.add_recipe(
        failure_signature=failure_signature(colour_only_task(rng)[0]),
        cluster_label="colour-only", module_name="recolor_relational_v1",
        module_desc="x", lift_before=0.1, lift_after=0.4, task_ids_fixed=["a1"],
        notes="", ts="2026-07-23T00:00:00Z", path=p,
    )
    RL.add_recipe(
        failure_signature=failure_signature(object_removal_task(rng)[0]),
        cluster_label="count-change", module_name="object_remove_v1",
        module_desc="y", lift_before=0.05, lift_after=0.3, task_ids_fixed=["c1"],
        notes="", ts="2026-07-23T00:05:00Z", path=p,
    )
    hits = RL.query_by_module("object_remove_v1", path=p)
    assert len(hits) == 1 and hits[0]["ts"] == "2026-07-23T00:05:00Z"
    assert RL.query_by_module("does_not_exist", path=p) == []


def test_empty_ledger_reads_empty(tmp_path):
    assert RL.all_recipes(path=tmp_path / "nope.json") == []
