# -*- coding: utf-8 -*-
"""Durable seed for the meta-diagnosis recipe ledger.

The ledger JSON (data/meta_diagnosis/recipes.json) is a RUNTIME-grown file (gitignored — the
acquisition loop appends recipes autonomously), so the initial, human-verified recipes live HERE as
committed code and are (re)seeded idempotently. This is the flywheel's seed, reproducible from source.

Recipe #1 is the first PHYSICAL instance of the owner's "recipe = data" flywheel: A4 hit the
relational-colour-recolor failure family, forged ``strat_relational_recolor``, and MEASURED the lift
(sealed ARC-1 2.5%->3.0%, +2, attempted-but-wrong=0, independently re-verified). The failure-signature
is built from a SYNTHETIC exemplar of the family (no sealed-eval content is learned); the fixed
task-ids are bare labels only.
"""
from __future__ import annotations

from typing import Sequence

from packages.meta_diagnosis.failure_signature import failure_signature, characterize_cluster, delta_features
from packages.meta_diagnosis.recipe_ledger import add_recipe, all_recipes

Grid = list[list[int]]

# Synthetic exemplar of the RELATIONAL-COLOUR-RECOLOR family (structural, NOT eval content):
# shape preserved, an object's colour becomes a REFERENCED object's colour; two pairs force a
# function (not a constant).
_RELATIONAL_RECOLOR: list[tuple[Grid, Grid]] = [
    ([[0, 1, 1, 0, 0], [0, 1, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 2, 2, 0], [0, 0, 2, 2, 0]],
     [[0, 1, 1, 0, 0], [0, 1, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 1, 1, 0], [0, 0, 1, 1, 0]]),
    ([[3, 3, 0, 0, 0], [3, 3, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 4, 4], [0, 0, 0, 4, 4]],
     [[3, 3, 0, 0, 0], [3, 3, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 3, 3], [0, 0, 0, 3, 3]]),
]

_RECIPE_1_TS = "2026-07-23T00:00:00Z"

# Synthetic exemplar of the LEGEND-READING family (structural, NOT eval content): a key region in
# the grid (here a legend row "8->5") defines a per-grid colour map; the legend is consumed in the
# output (dims change), the body is recoloured per the parsed map. This is the family the loop
# correctly ABSTAINED on before A5 forged the module (best_sim 0.43 vs recipe #1).
_LEGEND_READING: list[tuple[Grid, Grid]] = [
    ([[8, 5, 0, 0], [0, 0, 8, 8], [0, 0, 8, 8]],
     [[5, 5], [5, 5]]),
]

_RECIPE_2_TS = "2026-07-23T12:00:00Z"

# Synthetic exemplar of the legend-APPLICATION-grammar family (structural, NOT eval content):
# shape preserved, each object recoloured by a richer application rule (an orientation-canonical
# shape dictionary / attached marker / periodic tile index) rather than a single-attribute or flat
# colour map. Two pairs with different palettes force a per-grid FUNCTION, not a constant.
_APPLICATION_GRAMMAR: list[tuple[Grid, Grid]] = [
    ([[1, 1, 0, 2, 0], [1, 0, 0, 2, 2], [0, 0, 0, 0, 0], [3, 3, 0, 4, 0], [0, 3, 0, 4, 4]],
     [[5, 5, 0, 6, 0], [5, 0, 0, 6, 6], [0, 0, 0, 0, 0], [6, 6, 0, 5, 0], [0, 6, 0, 5, 5]]),
    ([[2, 2, 0, 1, 0], [2, 0, 0, 1, 1], [0, 0, 0, 0, 0], [4, 4, 0, 3, 0], [0, 4, 0, 3, 3]],
     [[6, 6, 0, 5, 0], [6, 0, 0, 5, 5], [0, 0, 0, 0, 0], [5, 5, 0, 6, 0], [0, 5, 0, 6, 6]]),
]

_RECIPE_3_TS = "2026-07-23T18:00:00Z"


def seed_known_recipes(*, path: str | None = None) -> int:
    """Idempotently seed the human-verified recipes into the ledger. Returns #recipes added."""
    existing = {(r.get("module_name"), r.get("ts")) for r in all_recipes(path=path)}
    added = 0

    if ("strat_relational_recolor", _RECIPE_1_TS) not in existing:
        pairs = _RELATIONAL_RECOLOR
        add_recipe(
            failure_signature=failure_signature(pairs),
            cluster_label=characterize_cluster([delta_features(pairs)]),
            module_name="strat_relational_recolor",
            module_desc=(
                "Relational colour-function deduction (packages/arc_agi/objects.py:977): colour = a "
                "referenced object's colour (adjacency/containment/shape-twin/enclosed-content) or a "
                "relational key->colour table; derive-then-verify EXACT on the task's own train "
                "pairs, MDL-ordered, abstains on undefined reference / unseen key."
            ),
            lift_before=0.025,
            lift_after=0.030,
            task_ids_fixed=["45737921", "7d1f7ee8"],
            notes=(
                "A4 sealed ARC-1 2.5%->3.0% (+2, attempted-but-wrong=0, re-verified). Cracks 2 of "
                "~25 relational-recolor tasks; the bulk need LEGEND/shape-dictionary reading (next "
                "lever, categorically different)."
            ),
            ts=_RECIPE_1_TS,
            path=path,
        )
        added += 1

    if ("legend_strategies", _RECIPE_2_TS) not in existing:
        pairs = _LEGEND_READING
        add_recipe(
            failure_signature=failure_signature(pairs),
            cluster_label=characterize_cluster([delta_features(pairs)]),
            module_name="legend_strategies",
            module_desc=(
                "Legend / in-grid-table reading front-end (packages/arc_agi/legend.py): detect a "
                "candidate key region (corner separable block / framed corner cell / marker shape), "
                "parse it into a colour->colour map or shape->colour dictionary, apply to the body; "
                "propose-verify EXACT on the task's own train pairs, MDL-ordered, abstains when no "
                "candidate legend yields an exact-consistent map."
            ),
            lift_before=0.030,
            lift_after=0.0375,
            task_ids_fixed=["0becf7df", "009d5c81", "1e81d6f9"],
            notes=(
                "A5 sealed ARC-1 3.0%->3.75% (+3, attempted-but-wrong=0, re-verified). The family "
                "the loop honestly abstained on after A4 (novel-family reason) — recipe #2 closes "
                "that abstention. Residual tasks need richer APPLICATION grammar "
                "(orientation-invariant templates / periodic tiling / attached markers) = A6."
            ),
            ts=_RECIPE_2_TS,
            path=path,
        )
        added += 1

    if ("application_strategies", _RECIPE_3_TS) not in existing:
        pairs = _APPLICATION_GRAMMAR
        add_recipe(
            failure_signature=failure_signature(pairs),
            cluster_label=characterize_cluster([delta_features(pairs)]),
            module_name="application_strategies",
            module_desc=(
                "Legend APPLICATION grammar (packages/arc_agi/application.py): D4 orientation-"
                "canonical shape dictionary, per-object attached-marker recolour, and periodic-"
                "lattice tile-indexed recolour; general Chollet symmetry/periodicity priors, "
                "propose-verify EXACT on the task's own train pairs, MDL-ordered, abstains on "
                "inconsistent."
            ),
            lift_before=0.0375,
            lift_after=0.045,
            task_ids_fixed=["845d6e51", "604001fa", "33b52de3"],
            notes=(
                "A6 sealed ARC-1 3.75%->4.50% (+3, attempted-but-wrong=0). Cracked 3 of 4 residual "
                "legend-application tasks; d94c3b52 abstains (additive periodic pattern-completion "
                "= a distinct grammar). Cap relocated from legend-application to pattern-completion."
            ),
            ts=_RECIPE_3_TS,
            path=path,
        )
        added += 1

    return added


if __name__ == "__main__":
    n = seed_known_recipes()
    print(f"seeded {n} recipe(s); ledger now holds {len(all_recipes())}")
    for i, r in enumerate(all_recipes()):
        print(f"  #{i+1} {r['module_name']} [{r['cluster_label']}] "
              f"{r['lift_before']}->{r['lift_after']} fixed={r['task_ids_fixed']}")
