# -*- coding: utf-8 -*-
"""Register the repo-engineering learned bit in the neuro ledger — as a ~0-param, non-fact-source row.

The repo-engineering wave introduces NO trained weights. Its two moving parts are both curated
STRUCTURE, not learned parameters, exactly the category the ledger already counts at 0 for
``fluency_register_lever`` and ``conversation_engage``:

  * the edit-SCHEMA families (operand-substitution, block-deletion, comparison-flip, ...) are
    domain-blind program-transformation rules — the same kind of curated data as fluency's register
    skeletons, never trained weights;
  * the verified edit-shape LIBRARY (``data/repo_engineering/library.jsonl``) stores which schema
    resolved which instance shape, so a verified transform is recalled + RE-verified — a compounding
    cache, not a model; its float-count is 0 (ids and counts, no weight arrays).

Following the self_evolution ``ledger_contribution`` precedent, this module EXPOSES the ``Organ``
declaration + a budget check WITHOUT editing packages/neuro_ledger/ledger.py (that registry is owned
elsewhere and protected from self-mod). The card is a plain JSON with no float weight arrays, so
``measure_params`` counts exactly 0 and the No-LLM parameter budget can SEE it is 0.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.neuro_ledger.ledger import Artifact, Organ, measure_params

REPO = Path(__file__).resolve().parents[2]


def _card_path() -> Path:
    d = REPO / "data" / "repo_engineering"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ledger_card.json"


def write_card() -> Path:
    """Persist the ledger card — deliberately NO weight arrays, so measured params == 0."""
    card = {
        "id": "repo_engineering_edit_schemas",
        "role": "domain-blind structural edit-schema families + a verified edit-shape library; "
                "proposes candidate patches that the regression gate verifies",
        "learned_params": 0,
        "fact_source": False,
        "note": "curated program-transformation structure (like fluency register skeletons) + a "
                "re-verified shape cache — no trained weights",
    }
    p = _card_path()
    p.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def organ() -> Organ:
    """The neuro-ledger Organ for the repo-engineering edit schemas (0 params, not a fact source)."""
    write_card()
    return Organ(
        id="repo_engineering_edit_schemas",
        path="packages/swe_eval/edit_schemas.py",
        role="domain-blind edit-schema PROPOSER for repo-scale patches (operand-substitution, "
             "block-deletion, comparison/boolean flips, guard/return toggles) + a verified edit-shape "
             "library; every proposal is gated by the regression verifier — never a fact source, and "
             "holds no trained weights (curated transformation structure)",
        gate="swe_eval patch_pipeline behind the regression gate (FAIL_TO_PASS+PASS_TO_PASS green; "
             "fail-0 abstain otherwise)",
        artifacts=[Artifact("data/repo_engineering/ledger_card.json", "json_floats", role="metadata")],
        fact_source=False,
        enforced=False,          # advisory tier: a 0-param structural proposer, not an answer-path model
        status="active",
        fallback_params=0,
    )


def budget_check() -> dict[str, Any]:
    """Measure the real footprint. INVARIANT: 0 params, not a fact source."""
    o = organ()
    m = measure_params(o)
    params = int(m.get("params", 0))
    return {"id": o.id, "params": params, "fact_source": o.fact_source,
            "ok": params == 0 and o.fact_source is False,
            "measured": m.get("measured"), "present": m.get("present")}
