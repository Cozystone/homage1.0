# -*- coding: utf-8 -*-
"""Meta-diagnosis (Switch 2 v0: RETRIEVAL) — propose a fix module for a failure by recalling the
nearest past recipe. Honestly ABSTAINS when nothing near is on record.

The owner's honest gap map (docs/ATANOR_meta_diagnosis_loop.md, Switch 2):
  * v0 — RETRIEVAL (tractable, THIS FILE): match a new failure-signature against the recipe ledger;
          if a past recipe's failure resonates closely enough, propose the module that fixed it.
  * v1 — GENERATIVE (frontier, NOT built): invent a genuinely-new module for a failure family never
          seen before. That needs a compositional rich meta-basis + a failure->composition
          recognizer. It is a deliberate NotImplementedError stub (``propose_novel_module``).

``diagnose`` never fabricates a module name: below the similarity threshold it returns
``proposal=None`` with the honest "novel failure family" reason. This is the propose-verify
discipline — a proposal is only ever a RECALLED, previously-verified recipe, and the operator-signed
commit floor (Switch 3) still sits downstream. Pure-Python + numpy; no network.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from packages.vsa_reasoning.fhrr_core import resonance
from packages.meta_diagnosis.recipe_ledger import all_recipes, recipe_signature

# Retrieval floor. Same scale as the clustering threshold: within-family failures resonate ~1.0, a
# different family ~0.5 (roles orthogonal → resonance ≈ fraction of agreeing delta features), so a
# floor in the gap admits near-duplicates and rejects novel families.
DEFAULT_RETRIEVAL_THRESHOLD = 0.75

NOVEL_REASON = "novel failure family — needs generative meta-hypothesis (frontier)"


def diagnose(
    new_failure_signature: np.ndarray,
    *,
    path: str | None = None,
    threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
    top_k: int = 3,
) -> dict[str, Any]:
    """Diagnose a new failure by RETRIEVAL over the recipe ledger.

    Rank recipes by phasor resonance of their stored failure-signature to ``new_failure_signature``.
    If the best resonance >= ``threshold`` PROPOSE that recipe's module (confidence = resonance);
    otherwise ABSTAIN with ``proposal=None`` and the honest novel-family reason. Never invents a
    module name.

    Returns::

        {"proposal": {"module_name", "module_desc", "confidence", "cluster_label", "via_recipe_ts"}
                     | None,
         "best_similarity": float,
         "matches": [{"module_name", "cluster_label", "similarity"}, ...],   # top_k, for audit
         "reason": <present only when proposal is None>}
    """
    recipes = all_recipes(path=path)
    if not recipes:
        return {"proposal": None, "reason": NOVEL_REASON, "best_similarity": 0.0, "matches": []}

    scored: list[tuple[float, dict[str, Any]]] = []
    for rec in recipes:
        try:
            sig = recipe_signature(rec)
        except Exception:
            continue
        scored.append((float(resonance(new_failure_signature, sig)), rec))
    if not scored:
        return {"proposal": None, "reason": NOVEL_REASON, "best_similarity": 0.0, "matches": []}

    scored.sort(key=lambda t: t[0], reverse=True)
    matches = [
        {
            "module_name": rec.get("module_name"),
            "cluster_label": rec.get("cluster_label"),
            "similarity": round(sim, 4),
        }
        for sim, rec in scored[: max(1, top_k)]
    ]
    best_sim, best_rec = scored[0]

    if best_sim >= threshold:
        return {
            "proposal": {
                "module_name": best_rec.get("module_name"),
                "module_desc": best_rec.get("module_desc"),
                "confidence": round(best_sim, 4),
                "cluster_label": best_rec.get("cluster_label"),
                "via_recipe_ts": best_rec.get("ts"),
            },
            "best_similarity": round(best_sim, 4),
            "matches": matches,
        }
    return {
        "proposal": None,
        "reason": NOVEL_REASON,
        "best_similarity": round(best_sim, 4),
        "matches": matches,
    }


def propose_novel_module(new_failure_signature: np.ndarray, cluster_descriptor: str | None = None):
    """FRONTIER STUB — Switch 2 v1 (generative meta-hypothesis). NOT built.

    Inventing a genuinely-new fix module for a failure family that has NO near recipe is the deepest
    gap in the loop (docs/ATANOR_meta_diagnosis_loop.md, Switch 2 v1). It requires a compositional
    rich meta-basis plus a failure->composition recognizer, and it is exactly the one place a small
    learned recognizer could earn its keep under the neuro budget. This v0 does NOT attempt it: it
    only RETRIEVES known recipes (see ``diagnose``) and abstains on novel families. Do not fake it."""
    raise NotImplementedError(
        "Switch 2 v1 (generative meta-hypothesis / novel-module invention) is not implemented. "
        "meta_diagnosis v0 only RETRIEVES known recipes via diagnose(); it abstains on novel "
        "failure families. See docs/ATANOR_meta_diagnosis_loop.md (Switch 2 v1)."
    )
