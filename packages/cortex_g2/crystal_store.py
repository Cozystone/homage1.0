from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .models import KnowledgeCrystal
from .storage import DEFAULT_CORTEX_ROOT, ensure_cortex_dirs, read_json, write_json


def _crystal_path(crystal_id: str, root: str | Path = DEFAULT_CORTEX_ROOT) -> Path:
    return Path(root) / "crystals" / f"{crystal_id}.json"


def _crystal_id(prediction_trace: dict[str, Any], workspace: dict[str, Any]) -> str:
    seed = {
        "query": workspace.get("query"),
        "observed": prediction_trace.get("observed_paths", []),
        "frame": workspace.get("frame_id"),
    }
    return f"kcr_{hashlib.sha256(repr(seed).encode('utf-8')).hexdigest()[:18]}"


def maybe_create_crystal(prediction_trace: dict[str, Any], workspace: dict[str, Any], *, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    ensure_cortex_dirs(root)
    observed = [row for row in prediction_trace.get("observed_paths", []) if isinstance(row, dict)]
    errors = [row for row in prediction_trace.get("prediction_errors", []) if isinstance(row, dict)]
    seed_anchors = [node for node in workspace.get("seed_anchors", []) if isinstance(node, dict)]
    cloud_nodes = [node for node in workspace.get("cloud_attached_nodes", []) if isinstance(node, dict)]
    evidence_backed = bool(observed and (seed_anchors or cloud_nodes))
    mean_error = float(prediction_trace.get("mean_prediction_error") or 0.0)
    if not evidence_backed or mean_error > 0.6:
        return {
            "created": False,
            "reason": "insufficient_evidence" if not evidence_backed else "prediction_error_too_high",
            "self_generated_truth_saved": False,
            "local_brain_write": False,
        }
    crystal_id = _crystal_id(prediction_trace, workspace)
    crystal = KnowledgeCrystal(
        crystal_id=crystal_id,
        crystal_type="explanation",
        trigger_concepts=[str(node.get("label") or node.get("node_id")) for node in workspace.get("salience_top_k", [])[:8] if isinstance(node, dict)],
        reasoning_path=observed,
        source_trace=[
            {"frame_id": workspace.get("frame_id"), "prediction_trace_id": prediction_trace.get("trace_id")},
            *[{"seed_anchor": node.get("node_id"), "label": node.get("label")} for node in seed_anchors[:6]],
            *[{"cloud_node": node.get("node_id"), "label": node.get("label")} for node in cloud_nodes[:6]],
        ],
        success_count=0,
        failure_count=0,
        reuse_score=0.0,
        verification_state="candidate",
        created_from_self_generated_output=False,
    ).to_dict()
    write_json(_crystal_path(crystal_id, root), crystal)
    return {"created": True, "crystal": crystal, "self_generated_truth_saved": False, "local_brain_write": False}


def list_crystals(*, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    ensure_cortex_dirs(root)
    crystals = [read_json(path) for path in sorted((Path(root) / "crystals").glob("kcr_*.json"))]
    return {"crystals": crystals, "count": len(crystals), "local_brain_write": False}


def get_crystal(crystal_id: str, *, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    return read_json(_crystal_path(crystal_id, root), default={})


def reuse_crystal(query: str, *, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    query_l = query.casefold()
    candidates = []
    for crystal in list_crystals(root=root)["crystals"]:
        haystack = " ".join(str(value) for value in crystal.get("trigger_concepts", []))
        if any(part in haystack.casefold() for part in query_l.split()):
            crystal["reuse_score"] = round(float(crystal.get("reuse_score") or 0.0) + 0.1, 4)
            crystal["success_count"] = int(crystal.get("success_count") or 0) + 1
            write_json(_crystal_path(str(crystal["crystal_id"]), root), crystal)
            candidates.append(crystal)
    return {"matched": candidates, "count": len(candidates), "stored_as_truth": False}


def weaken_crystal(crystal_id: str, *, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    crystal = get_crystal(crystal_id, root=root)
    if not crystal:
        return {"updated": False, "reason": "not_found"}
    crystal["failure_count"] = int(crystal.get("failure_count") or 0) + 1
    crystal["reuse_score"] = max(0.0, float(crystal.get("reuse_score") or 0.0) - 0.12)
    if crystal["failure_count"] >= 3:
        crystal["verification_state"] = "rejected"
    write_json(_crystal_path(crystal_id, root), crystal)
    return {"updated": True, "crystal": crystal}


def promote_crystal(crystal_id: str, *, user_approved: bool = False, root: str | Path = DEFAULT_CORTEX_ROOT) -> dict[str, Any]:
    crystal = get_crystal(crystal_id, root=root)
    if not crystal:
        return {"promoted": False, "reason": "not_found"}
    if not user_approved:
        return {"promoted": False, "reason": "user_approval_required", "local_brain_write": False}
    crystal["verification_state"] = "verified"
    write_json(_crystal_path(crystal_id, root), crystal)
    return {"promoted": True, "crystal": crystal, "local_brain_write": False}
