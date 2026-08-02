# -*- coding: utf-8 -*-
"""Register the self-evolution orchestrator in the neuro ledger — as a ~0-param control organ.

The orchestrator holds NO learned weights. It reads scorecards, ranks by arithmetic, and dispatches or
flags loops. That is a control instrument, not a model — so its parameter footprint is 0, and the
neuro budget (the machinery that keeps the No-LLM brain from silently growing into an LLM) must be able
to SEE that it is 0.

We declare it using neuro_ledger's own ``Organ`` dataclass (so the same measurement machinery applies)
and persist a tiny ledger card with NO weight arrays. We do NOT edit packages/neuro_ledger/ledger.py
(that registry is owned elsewhere and is constitutionally protected from self-mod); this module simply
EXPOSES the organ declaration + a budget check the self-evolution tests pin. The card is a plain JSON
with no float weight arrays, so ``measure_params`` counts 0 and the unregistered-artifact detector
ignores it (a .json is not a model-like extension).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.neuro_ledger.ledger import Artifact, Organ, measure_params


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _card_path() -> Path:
    d = repo_root() / "data" / "self_evolution"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ledger_card.json"


def write_card() -> Path:
    """Persist the ledger card. Deliberately contains NO weight arrays (keys the float-counter reads),
    so its measured parameter count is exactly 0."""
    card = {
        "id": "self_evolution_orchestrator",
        "role": "reads scorecards, ranks deficiencies by impact x evolvability, dispatches "
                "verifier-backed loops or flags operator proposals",
        "learned_params": 0,
        "fact_source": False,
        "note": "control instrument, not a model — no learned weights",
    }
    p = _card_path()
    p.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def organ() -> Organ:
    """The neuro-ledger Organ describing the orchestrator (0 params, not a fact source, advisory tier).

    Ensures the card exists so ``measure_params`` measures a real on-disk artifact at 0 params rather
    than falling back to a declared count."""
    write_card()
    return Organ(
        id="self_evolution_orchestrator",
        path="packages/self_evolution/orchestrator.py",
        role="broad self-evolution orchestrator: maps deficiencies to verifier-backed loops; holds no "
             "learned weights (control logic only)",
        gate="self_evolution wireheading guard + neuro budget (this declaration)",
        artifacts=[Artifact("data/self_evolution/ledger_card.json", "json_floats", role="metadata")],
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
