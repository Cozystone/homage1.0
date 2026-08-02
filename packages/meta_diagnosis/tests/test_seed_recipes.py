# -*- coding: utf-8 -*-
"""Seeder: recipe #1 seeds idempotently and is retrievable by the loop."""
from __future__ import annotations

import os

from packages.meta_diagnosis.seed_recipes import seed_known_recipes, _RELATIONAL_RECOLOR
from packages.meta_diagnosis.recipe_ledger import all_recipes
from packages.meta_diagnosis.failure_signature import failure_signature
from packages.meta_diagnosis.meta_diagnose import diagnose


def _ledger(tmp_path) -> str:
    return os.path.join(str(tmp_path), "recipes.json")


def test_seed_is_idempotent(tmp_path):
    p = _ledger(tmp_path)
    assert seed_known_recipes(path=p) == 3          # first seed adds recipes #1, #2, #3
    assert seed_known_recipes(path=p) == 0          # second is a no-op
    recs = all_recipes(path=p)
    assert len(recs) == 3
    assert recs[0]["module_name"] == "strat_relational_recolor"
    assert recs[0]["lift_before"] == 0.025 and recs[0]["lift_after"] == 0.030
    assert recs[0]["task_ids_fixed"] == ["45737921", "7d1f7ee8"]
    assert recs[1]["module_name"] == "legend_strategies"
    assert recs[1]["lift_before"] == 0.030 and recs[1]["lift_after"] == 0.0375
    assert recs[1]["task_ids_fixed"] == ["0becf7df", "009d5c81", "1e81d6f9"]
    assert recs[2]["module_name"] == "application_strategies"
    assert recs[2]["lift_before"] == 0.0375 and recs[2]["lift_after"] == 0.045
    assert recs[2]["task_ids_fixed"] == ["845d6e51", "604001fa", "33b52de3"]


def test_seeded_recipe_is_retrievable(tmp_path):
    p = _ledger(tmp_path)
    seed_known_recipes(path=p)
    # a matching relational-recolor failure retrieves the seeded module at high confidence
    sig = failure_signature(_RELATIONAL_RECOLOR)
    out = diagnose(sig, path=p)
    assert out["proposal"] is not None
    assert out["proposal"]["module_name"] == "strat_relational_recolor"
    assert out["best_similarity"] >= 0.99


def test_legend_family_now_retrieves_recipe_2(tmp_path):
    """The family the loop ABSTAINED on after A4 now retrieves recipe #2 — the loop closed."""
    from packages.meta_diagnosis.seed_recipes import _LEGEND_READING

    p = _ledger(tmp_path)
    seed_known_recipes(path=p)
    out = diagnose(failure_signature(_LEGEND_READING), path=p)
    assert out["proposal"] is not None
    assert out["proposal"]["module_name"] == "legend_strategies"
    assert out["best_similarity"] >= 0.99
