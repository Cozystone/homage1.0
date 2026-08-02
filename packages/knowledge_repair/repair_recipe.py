# -*- coding: utf-8 -*-
"""Register a knowledge repair as a RECIPE, so the next one is retrieved rather than re-invented.

`meta_diagnosis` already holds the retrieval half: match a new failure's FHRR signature against
past recipes and propose the module that fixed the nearest one, abstaining below threshold. It was
unreachable from here for a mechanical reason -- `encode_features` iterated a hard-coded ARC role
vocabulary, so only grid tasks could be encoded. That is now a parameter (the algorithm never knew
what a role meant; it builds atoms from strings), and the workaround it removes was already
visible: `self_acceleration/trace_signature.py` copies the same function verbatim for a second
domain.

WHAT THIS IS AND IS NOT. Registering a recipe lets ATANOR RE-APPLY a repair shape it has seen to a
similar failure. It does not let it invent a repair for an unseen one -- that is
`meta_diagnose.propose_novel_module`, which raises NotImplementedError and is the declared
frontier. The honest description is re-application, not invention. But an empty ledger makes
retrieval vacuous, so this is the prerequisite for the frontier rather than a substitute for it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

# The vocabulary a KNOWLEDGE-repair failure is described by. Chosen to be the things that actually
# distinguish one such failure from another -- not a description of the subject, which would make
# every merged node its own family and defeat retrieval entirely.
REPAIR_ROLES = (
    "defect_kind",         # what went wrong structurally (e.g. "merged_referent")
    "predicate_class",     # functional / multi-valued -- decides whether a conflict IS a defect
    "conflict_degree",     # how many competing values: "two" / "few" / "many"
    "evidence_in_graph",   # can the graph settle it alone? (drives whether acquisition is needed)
    "residue_trend",       # what repeated rounds did: "falling" / "stalled" / "unknown"
)


def repair_features(*, defect_kind: str, functional: bool, n_values: int,
                    evidence_in_graph: bool, residue_trend: str = "unknown") -> dict[str, Any]:
    """Describe one knowledge-repair failure in the fixed repair vocabulary.

    `conflict_degree` is bucketed rather than exact on purpose: retrieval should treat a 5-value
    and a 7-value merge as the same family. Exact counts would make every node unique and the
    ledger would never match anything."""
    degree = "two" if n_values <= 2 else ("few" if n_values <= 6 else "many")
    return {
        "defect_kind": str(defect_kind),
        "predicate_class": "functional" if functional else "multi_valued",
        "conflict_degree": degree,
        "evidence_in_graph": bool(evidence_in_graph),
        "residue_trend": str(residue_trend),
    }


def repair_signature(features: dict[str, Any]):
    """FHRR signature of a knowledge-repair failure, in the SAME space ARC failures use.

    Same space matters: it is what lets one ledger serve both, so a future domain does not need a
    third copy of the algebra."""
    from packages.meta_diagnosis.failure_signature import encode_features
    return encode_features(features, REPAIR_ROLES)


def register(*, features: dict[str, Any], module_name: str, module_desc: str,
             coverage_before: float, coverage_after: float,
             subjects_fixed: Iterable[str], notes: str, ts: str,
             path: str | Path | None = None) -> dict[str, Any]:
    """Record a repair that measurably worked, in the shared recipe ledger.

    `coverage_before/after` go in as the ledger's lift fields: a recipe is only worth retrieving if
    it moved a number, and coverage is the number this repair moves."""
    from packages.meta_diagnosis.recipe_ledger import add_recipe
    return add_recipe(
        failure_signature=repair_signature(features),
        cluster_label=str(features.get("defect_kind", "unknown")),
        module_name=module_name,
        module_desc=module_desc,
        lift_before=float(coverage_before),
        lift_after=float(coverage_after),
        task_ids_fixed=list(subjects_fixed),
        notes=notes,
        ts=ts,
        path=path,
    )
