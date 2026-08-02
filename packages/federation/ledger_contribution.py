# -*- coding: utf-8 -*-
"""Register the federation orchestrator in the neuro ledger — as a ~0-param control organ.

The federation machinery holds NO learned weights. The orchestrator ranks nothing and trains nothing;
the sealed judge is a deterministic INTERPRETER (a verifier). So the whole package's learned-parameter
footprint is 0, and the neuro budget (the guard that keeps the No-LLM brain from silently growing into
an LLM) must be able to SEE it is 0.

We declare it with neuro_ledger's own ``Organ`` dataclass (same measurement machinery) and persist a
card with NO weight arrays. We do NOT edit packages/neuro_ledger/ledger.py (owned elsewhere,
constitutionally immutable) — this module only EXPOSES the declaration + a budget check.

HONESTY on federated organ-param capabilities: when a *node* contributes an ``organ-param`` capability
and it is promoted, those weights are learned parameters — but they live on each ADOPTING NODE, and are
governed by THAT node's neuro ledger when adopted. The orchestrator merely moves the structure; it
stores no weights of its own. ``promoted_param_footprint()`` sums the declared param counts of promoted
organ-param capabilities so an adopting node's budget can account for them honestly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.neuro_ledger.ledger import Artifact, Organ, measure_params


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _card_path() -> Path:
    d = repo_root() / "data" / "federation"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ledger_card.json"


def write_card() -> Path:
    """Persist the ledger card. Deliberately carries NO weight-array keys (weights/bias/mean/...), so
    the float-counter measures exactly 0 parameters."""
    card = {
        "id": "federation_orchestrator",
        "role": "collects self-evolved nodes' capability SHAPES, blind-judges them on a sealed "
                "holdout, integrates the promoted ones into a signed universal generation, and "
                "redistributes; shares ABILITY, never personhood/data",
        "learned_params": 0,
        "fact_source": False,
        "note": "control instrument + deterministic verifier — no learned weights; promoted "
                "organ-param capabilities are accounted to each adopting node's ledger",
    }
    p = _card_path()
    p.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def organ() -> Organ:
    """The neuro-ledger Organ describing the federation orchestrator (0 params, not a fact source,
    advisory tier). Ensures the card exists so measure_params reads a real 0-param artifact."""
    write_card()
    return Organ(
        id="federation_orchestrator",
        path="packages/federation/orchestrator.py",
        role="federated capability evolution: sealed-judge promotion of capability SHAPES into a "
             "signed, rollbackable universal layer; holds no learned weights (control + verifier)",
        gate="federation sealed judge + two-layer split + neuro budget (this declaration)",
        artifacts=[Artifact("data/federation/ledger_card.json", "json_floats", role="metadata")],
        fact_source=False,
        enforced=False,          # advisory tier: a 0-param control organ, not an answer-path model
        status="active",
        fallback_params=0,
    )


def budget_check() -> dict[str, Any]:
    """Measure the orchestrator's real parameter footprint. INVARIANT: 0 params, not a fact source."""
    o = organ()
    m = measure_params(o)
    params = int(m.get("params", 0))
    return {
        "id": o.id,
        "params": params,
        "fact_source": o.fact_source,
        "ok": params == 0 and o.fact_source is False,
        "measured": m.get("measured"),
        "present": m.get("present"),
    }


def promoted_param_footprint(universal_layer: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Sum the DECLARED learned-parameter counts of promoted ``organ-param`` capabilities in a
    universal layer. Schemas and routers carry 0 learned params (they are symbolic structure). This is
    the number an adopting node's neuro budget must add when it installs the universal floor."""
    total = 0
    per_cap: list[dict[str, Any]] = []
    for cid, cap in universal_layer.items():
        if cap.get("capability_kind") != "organ-param":
            continue
        w = cap.get("payload", {}).get("weights", []) or []
        n = len(w) + (1 if "bias" in cap.get("payload", {}) else 0)
        total += n
        per_cap.append({"capability_id": cid, "params": n})
    return {"organ_param_total": total, "per_capability": per_cap,
            "note": "accounted to each ADOPTING node's neuro ledger; the orchestrator stores no weights"}
