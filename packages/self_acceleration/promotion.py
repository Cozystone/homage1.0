# -*- coding: utf-8 -*-
"""H4 v3 — OPERATOR-SIGNED PROMOTION of the cross-family transfer recipes into the shared recipe bank.

The candidate-promotion-gate is default-DENY: recipes only enter the shared meta-diagnosis recipe bank
(`data/meta_diagnosis/recipes.json`) on an explicit operator sign-off. This module performs that promotion
ONE way — SAFELY and REVERSIBLY — so the H4 v3 open-ended cross-family transfer capability (the
`SignatureCoupledRecognizer` + the verified cross-family scheme recipes, source commit 04bed064) becomes
permanent and compounding:

  * ADDITIVE  — existing recipes are never overwritten or deleted; new recipes are appended.
  * IDEMPOTENT — each promoted recipe carries a `promo_id` (commit:wall:scheme); a re-run skips any
                 promo_id already present, so promotion cannot double-write.
  * ATOMIC    — the bank is rewritten via a temp file + os.replace (a concurrent reader — e.g. a gauge
                 agent — always sees either the whole old file or the whole new file, never a partial).
  * BACKED UP — the caller records a timestamped backup before the write; this module also writes its own
                 sibling backup, so rollback is always a file copy away.
  * PROVENANCE — every promoted entry is stamped operator-signed (operator, approval date, source commit,
                 capability) in `module_desc` + `notes`.

The recipes themselves are the VERIFIED crossings of the coupled full-4-family flywheel: every one was
re-executed on held-out examples (`od.fitness >= 1.0`) before it was recorded — propose-verify, zero
fabrication. This module invents nothing; it persists what was already verified. No-LLM, stdlib + numpy.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from packages.meta_diagnosis import recipe_ledger as _bank
from packages.self_acceleration import cross_family_v3 as cf3

CAPABILITY = "H4 v3 open-ended cross-family transfer"
SOURCE_COMMIT = "04bed064"
CLUSTER_LABEL = "h4_v3_cross_family_transfer"
MODULE_NAME = "self_acceleration::SignatureCoupledRecognizer"


def _scheme_label(scheme: dict) -> str:
    if scheme.get("family") == "projection_chain":
        return f"projection_chain(depth={scheme.get('depth')})"
    aux = scheme.get("aux") or []
    return f"computed_projection({{{','.join(aux)}}})"


def build_v3_ledger_records(seed: int = 7) -> tuple[list[dict], dict]:
    """Run the coupled full-4-family flywheel and return its VERIFIED crossing records
    (failure_signature -> scheme -> wall). Each record is a wall the coupled recogniser crossed and the
    loop RE-EXECUTED on holdout (propose-verify). Returns (records, run) — run carries walls_crossed etc."""
    run = cf3.run_cross_family_v3("v3", variant="coupled", seed=seed)
    records = list(run["state"]["ledger"]._records)
    return records, run


def _existing_promo_ids(existing: list[dict]) -> set[str]:
    ids: set[str] = set()
    for r in existing:
        try:
            pid = json.loads(r.get("module_desc", "{}")).get("promo_id")
        except Exception:
            pid = None
        if pid:
            ids.add(pid)
    return ids


def _atomic_write(path: Path, recipes: list[dict]) -> None:
    """Write the full recipe list atomically: temp file in the same dir, flush+fsync, os.replace. A
    concurrent reader never sees a partially-written bank."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".recipes.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(recipes, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)                       # atomic on the same filesystem
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def promote(*, operator: str, approved: str, ts: str, path: str | Path | None = None, seed: int = 7,
            sibling_backup: bool = True) -> dict[str, Any]:
    """ADDITIVELY promote the verified H4 v3 cross-family recipes into the shared bank, operator-signed.

    Returns an audit dict: bank_path, sibling_backup_path, total_before/after, added/skipped promo_ids,
    walls_crossed. Idempotent (skips promo_ids already present); atomic; existing recipes preserved."""
    bank_path = _bank._resolve(path)
    existing = _bank.all_recipes(path)
    sibling = None
    if sibling_backup and bank_path.exists():
        sibling = bank_path.with_name(f"recipes.presig_backup.{ts.replace(':', '').replace('-', '')}.json")
        shutil.copy2(bank_path, sibling)

    have = _existing_promo_ids(existing)
    records, run = build_v3_ledger_records(seed)
    provenance = {"operator": operator, "approved": approved, "source_commit": SOURCE_COMMIT,
                  "capability": CAPABILITY, "promoted_ts": ts}

    new_recipes: list[dict] = []
    added: list[str] = []
    skipped: list[str] = []
    for rec in records:
        scheme = rec["scheme"]
        wall = rec["wall"]
        label = _scheme_label(scheme)
        promo_id = f"{SOURCE_COMMIT}:{wall}:{label}"
        if promo_id in have:
            skipped.append(promo_id)
            continue
        desc = json.dumps({"scheme": scheme, "promo_id": promo_id, **provenance}, ensure_ascii=False)
        notes = (f"operator-signed promotion; operator={operator}; approved={approved}; "
                 f"commit={SOURCE_COMMIT}; capability={CAPABILITY}")
        new_recipes.append({
            "failure_signature": _bank.signature_to_list(rec["signature"]),
            "cluster_label": CLUSTER_LABEL,
            "module_name": MODULE_NAME,
            "module_desc": desc,
            "lift_before": 0.0,
            "lift_after": 1.0,
            "task_ids_fixed": [str(wall)],
            "notes": notes,
            "ts": str(ts),
        })
        added.append(promo_id)
        have.add(promo_id)

    final = existing + new_recipes
    _atomic_write(bank_path, final)
    return {
        "bank_path": str(bank_path),
        "sibling_backup_path": str(sibling) if sibling else None,
        "total_before": len(existing),
        "total_after": len(final),
        "added": added,
        "skipped": skipped,
        "walls_crossed": run["walls_crossed"],
        "walls_total": run["walls_total"],
    }
