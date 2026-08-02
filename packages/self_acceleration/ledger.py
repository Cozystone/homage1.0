# -*- coding: utf-8 -*-
"""H4 — SCHEME-RECIPE LEDGER: the data flywheel that turns retrieval into GENERATION.

A recipe is the record of a scheme that CROSSED a wall:

    failure_signature  ->  (scheme config that crossed it, incl. the promoted output-step template)  ->  lift

This is the exact substance `packages/meta_diagnosis/recipe_ledger.py` stores — we REUSE its signature
(de)serialisation (`signature_to_list` / `signature_from_list`) and the same JSON persistence shape, so
an H4 recipe round-trips through the meta-diagnosis store when the operator chooses to persist it. The
difference from Switch 2 v0 (`meta_diagnose.diagnose`, pure RETRIEVAL) is what the caller DOES with the
match: v0 replays the SAME module; H4's proposer takes the retrieved scheme as a STARTING POINT and
EXTENDS it (grow the accumulator, re-index the promoted step) to build a scheme never seen before — the
generative bridge. This module is only the STORE + the resonance retrieval; the generation is in
`proposer.py`.

The scheme config is JSON-serialisable (the promoted output-step template is stored as nested lists and
thawed back to the interpreter's tuple trees on retrieval). Deterministic, No-LLM, numpy + stdlib.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from packages.vsa_reasoning.fhrr_core import resonance
from packages.meta_diagnosis.recipe_ledger import (
    signature_to_list, signature_from_list, add_recipe as _persist_recipe, all_recipes as _load_recipes,
)

DEFAULT_RETRIEVAL_THRESHOLD = 0.75          # same scale as meta_diagnose: within-family ~1.0, cross ~0.5


def _thaw(x: Any) -> Any:
    """JSON round-trips tuples to lists; the interpreter needs tuple trees. Recursively list -> tuple."""
    if isinstance(x, list):
        return tuple(_thaw(e) for e in x)
    return x


class SchemeLedger:
    """In-memory bank of scheme recipes with FHRR-resonance retrieval. Optionally mirrors to the shared
    meta-diagnosis recipe store (operator-signed persistence)."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self._records)

    def add(self, sig: np.ndarray, scheme: dict[str, Any], wall: str, *,
            lift_before: float = 0.0, lift_after: float = 1.0) -> dict[str, Any]:
        """Record a verified wall-crossing. `scheme` is a JSON-able config dict (family, depth, aux
        names, and the promoted output-step template as nested lists)."""
        rec = {
            "signature": np.asarray(sig, dtype=np.complex128),
            "scheme": scheme,
            "wall": str(wall),
            "lift_before": float(lift_before),
            "lift_after": float(lift_after),
        }
        self._records.append(rec)
        return rec

    def retrieve(self, sig: np.ndarray, *, threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
                 top_k: int = 3, family: str | None = None) -> dict[str, Any]:
        """Rank stored recipes by phasor resonance to `sig`. Return the best above `threshold` (with its
        scheme config, templates thawed to tuple trees) plus the top_k audit list. Honestly abstains
        (best=None) below threshold — a genuinely novel family the proposer must build from the meta-basis
        with no seed (exactly the v0 abstention boundary, but here it FEEDS generation instead of stopping).
        `family` restricts the candidate pool to recipes of that scheme family (used to seed a specific
        move — e.g. only a projection-chain recipe can seed a projection-chain analogy)."""
        pool = [r for r in self._records if family is None or r["scheme"].get("family") == family]
        if not pool:
            return {"best": None, "best_similarity": 0.0, "matches": []}
        scored = sorted(((float(resonance(sig, r["signature"])), r) for r in pool),
                        key=lambda t: -t[0])
        matches = [{"wall": r["wall"], "family": r["scheme"].get("family"), "similarity": round(s, 4)}
                   for s, r in scored[: max(1, top_k)]]
        best_sim, best_rec = scored[0]
        if best_sim >= threshold:
            scheme = dict(best_rec["scheme"])
            if scheme.get("out_step_template") is not None:
                scheme = dict(scheme, out_step_template=_thaw(scheme["out_step_template"]))
            return {"best": {"scheme": scheme, "wall": best_rec["wall"], "similarity": round(best_sim, 4)},
                    "best_similarity": round(best_sim, 4), "matches": matches}
        return {"best": None, "best_similarity": round(best_sim, 4), "matches": matches}

    # --- optional persistence through the shared meta-diagnosis store (operator-signed) ---
    def persist_all(self, cluster_label: str = "synthesis-wall", ts: str = "", path: str | None = None) -> int:
        """Write every record to the meta-diagnosis recipe ledger (reusing its schema). Operator-signed:
        only called when the operator elects to promote H4's schemes into the shipped recipe bank. `ts`
        is passed in (deterministic). Returns the count written."""
        import json
        for r in self._records:
            _persist_recipe(
                failure_signature=r["signature"],
                cluster_label=cluster_label,
                module_name=f"h4_scheme::{r['scheme'].get('family')}::depth={r['scheme'].get('depth')}",
                module_desc=json.dumps(r["scheme"]),
                lift_before=r["lift_before"], lift_after=r["lift_after"],
                task_ids_fixed=[r["wall"]], notes="H4 self-invented scheme", ts=ts, path=path,
            )
        return len(self._records)


# module-level reuse anchors so callers can round-trip a signature exactly as the shared ledger does
sig_to_list = signature_to_list
sig_from_list = signature_from_list
load_persisted = _load_recipes
