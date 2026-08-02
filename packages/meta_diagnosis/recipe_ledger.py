# -*- coding: utf-8 -*-
"""Recipe ledger — the data-flywheel fuel for the meta-diagnosis loop (Switch 2 v0).

A *recipe* is the record of a fix that WORKED:

    failure_signature -> (named module that fixed it) -> measured lift

It is the exact substance the owner identified (docs/ATANOR_meta_diagnosis_loop.md, "레시피 =
데이터 플라이휠"): once a bank of recipes exists, an UNSEEN failure can be diagnosed by RETRIEVAL —
match its FHRR failure-signature against past recipes and propose the module that fixed the nearest
one (see ``meta_diagnose.diagnose``). This module is only the STORE; it invents nothing.

Recipe schema (one JSON object):
  * failure_signature : float vector — the FHRR failure-signature (complex phasor bundle) serialized
                        as an interleaved [re0, im0, re1, im1, ...] float list. Reconstruct with
                        ``signature_from_list`` / ``recipe_signature``.
  * cluster_label     : str  — the structural descriptor of the failure family (fixed vocabulary,
                        from ``failure_signature.characterize_cluster``).
  * module_name       : str  — the module that fixed the family.
  * module_desc       : str  — a human description of that module.
  * lift_before       : float — measured score BEFORE the module (propose-verify anchor).
  * lift_after        : float — measured score AFTER the module.
  * task_ids_fixed    : list  — task ids the module turned from fail -> pass.
  * notes             : str
  * ts                : str   — timestamp, PASSED IN by the caller (never generated here, so the
                        ledger stays deterministic and testable).

Persistence: a JSON list at ``data/meta_diagnosis/recipes.json`` (dir created on first write). All
functions accept an optional ``path=`` to redirect the store (tests use a temp file). Pure-Python +
numpy; no network; no heavy deps.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

# Canonical on-disk location (repo_root/data/meta_diagnosis/recipes.json). parents[2] == repo root,
# matching the sibling ledger in packages/flywheel/failure_receipts.py.
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "meta_diagnosis" / "recipes.json"

_RECIPE_FIELDS = (
    "failure_signature", "cluster_label", "module_name", "module_desc",
    "lift_before", "lift_after", "task_ids_fixed", "notes", "ts",
)


# --- signature (de)serialization: complex phasor bundle <-> JSON float list --------------------
def signature_to_list(z) -> list[float]:
    """Serialize a complex FHRR signature to an interleaved real float list [re0, im0, re1, ...].

    Accepts a complex ndarray or an already-serialized float list (idempotent pass-through)."""
    arr = np.asarray(z)
    if arr.dtype.kind == "c":
        flat = np.empty(arr.size * 2, dtype=np.float64)
        flat[0::2] = arr.real
        flat[1::2] = arr.imag
        return [float(x) for x in flat]
    # already a real float list/array (interleaved) — pass through as plain floats
    return [float(x) for x in np.asarray(arr, dtype=np.float64).ravel()]


def signature_from_list(xs: Sequence[float]) -> np.ndarray:
    """Reconstruct a complex FHRR signature from an interleaved [re, im, ...] float list."""
    flat = np.asarray(list(xs), dtype=np.float64)
    if flat.size % 2 != 0:
        raise ValueError("interleaved signature must have an even length")
    return flat[0::2] + 1j * flat[1::2]


def recipe_signature(recipe: dict) -> np.ndarray:
    """Reconstruct the complex failure-signature stored in a recipe dict."""
    return signature_from_list(recipe["failure_signature"])


# --- persistence ------------------------------------------------------------------------------
def _resolve(path: str | Path | None) -> Path:
    return Path(path) if path is not None else _DEFAULT_PATH


def _load(path: str | Path | None) -> list[dict[str, Any]]:
    p = _resolve(path)
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(path: str | Path | None, recipes: list[dict[str, Any]]) -> None:
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(recipes, fh, ensure_ascii=False, indent=2)


def add_recipe(
    *,
    failure_signature,
    cluster_label: str,
    module_name: str,
    module_desc: str,
    lift_before: float,
    lift_after: float,
    task_ids_fixed: Sequence[Any],
    notes: str,
    ts: str,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Append one recipe and persist. ``failure_signature`` may be a complex ndarray or an already
    interleaved float list. ``ts`` is passed in by the caller (deterministic). Returns the stored
    recipe dict."""
    rec: dict[str, Any] = {
        "failure_signature": signature_to_list(failure_signature),
        "cluster_label": str(cluster_label),
        "module_name": str(module_name),
        "module_desc": str(module_desc),
        "lift_before": float(lift_before),
        "lift_after": float(lift_after),
        "task_ids_fixed": [str(t) for t in (task_ids_fixed or [])],
        "notes": str(notes),
        "ts": str(ts),
    }
    recipes = _load(path)
    recipes.append(rec)
    _write(path, recipes)
    return rec


def all_recipes(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return every stored recipe (list of dicts). Empty list if the ledger does not exist."""
    return _load(path)


def query_by_module(name: str, path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the recipes whose ``module_name`` equals ``name``."""
    return [r for r in _load(path) if r.get("module_name") == name]
