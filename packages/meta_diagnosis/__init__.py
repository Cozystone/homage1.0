# -*- coding: utf-8 -*-
"""Meta-diagnosis loop — the FRONT-HALF infrastructure (Switches 1 + 2 v0) of the owner's
wrong-answer -> self-diagnose -> propose-module design (docs/ATANOR_meta_diagnosis_loop.md).

HONEST scope of this v0 (do not overclaim):
  * Switch 1 (a)-(c) — collect failures, FHRR-encode the I/O delta, CLUSTER into families: REAL
    (``failure_signature``). Cluster characterization uses a FIXED four-word delta vocabulary — a
    fixed rule, NOT a learned/open namer.
  * Switch 2 v0 — RETRIEVAL: match a failure against the recipe ledger, propose the module that
    fixed the nearest recorded family, ABSTAIN honestly below threshold: REAL (``meta_diagnose``).
  * Recipe ledger — the data-flywheel store that fuels retrieval: REAL (``recipe_ledger``).

Explicit FRONTIER (NOT built, marked as such):
  * Switch 1 (d) — mapping a cluster to a genuinely-NEW named hypothesis (open-vocab naming).
  * Switch 2 v1 — GENERATING a novel fix module for an unseen family
    (``meta_diagnose.propose_novel_module`` raises NotImplementedError).
  * Switch 3 — the operator-signed commit floor stays a human gate by constitution (wireheading
    immunity); this package proposes, it does not self-commit.

Substrate: the FHRR bind/unbind/resonance algebra is REUSED read-only from
``packages/vsa_reasoning`` (which itself reuses ``packages/cgsr/cgsr/holographic_lm.py``).
"""
from __future__ import annotations

from packages.meta_diagnosis.recipe_ledger import (
    add_recipe,
    all_recipes,
    query_by_module,
    recipe_signature,
    signature_to_list,
    signature_from_list,
)
from packages.meta_diagnosis.failure_signature import (
    delta_features,
    encode_features,
    failure_signature,
    cluster_signatures,
    characterize_cluster,
    DESCRIPTOR_VOCAB,
    DEFAULT_CLUSTER_THRESHOLD,
)
from packages.meta_diagnosis.meta_diagnose import (
    diagnose,
    propose_novel_module,
    DEFAULT_RETRIEVAL_THRESHOLD,
    NOVEL_REASON,
)

__all__ = [
    # recipe ledger
    "add_recipe",
    "all_recipes",
    "query_by_module",
    "recipe_signature",
    "signature_to_list",
    "signature_from_list",
    # failure signature (Switch 1 a-c)
    "delta_features",
    "encode_features",
    "failure_signature",
    "cluster_signatures",
    "characterize_cluster",
    "DESCRIPTOR_VOCAB",
    "DEFAULT_CLUSTER_THRESHOLD",
    # meta diagnose (Switch 2 v0)
    "diagnose",
    "propose_novel_module",
    "DEFAULT_RETRIEVAL_THRESHOLD",
    "NOVEL_REASON",
]
