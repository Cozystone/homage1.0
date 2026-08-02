from __future__ import annotations

import hashlib
from typing import Any

from .models import PredictionTrace
from .storage import DEFAULT_CORTEX_ROOT, append_jsonl, bounded_float, ensure_cortex_dirs, now_iso


CANONICAL_EXPECTATIONS = [
    {"source_concept": "Evidence", "relation": "supports", "target_concept": "Claim"},
    {"source_concept": "Source", "relation": "provides", "target_concept": "Evidence"},
    {"source_concept": "Verification", "relation": "evaluates", "target_concept": "Claim"},
    {"source_concept": "Evidence", "relation": "has_source", "target_concept": "Source"},
    {"source_concept": "Verification", "relation": "verifies", "target_concept": "Claim"},
]


def _trace_id(query: str) -> str:
    return f"ptr_{hashlib.sha256(f'{query}:{now_iso()}'.encode('utf-8')).hexdigest()[:18]}"


def _label(value: Any) -> str:
    return str(value or "").casefold()


def _node_matches(node: dict[str, Any], concept: str) -> bool:
    concept_l = concept.casefold()
    fields = [
        node.get("label"),
        node.get("concept_id"),
        node.get("node_id"),
        node.get("layer"),
    ]
    return any(concept_l in _label(field) for field in fields)


def _find_nodes(workspace: dict[str, Any], concept: str) -> list[dict[str, Any]]:
    return [node for node in workspace.get("active_nodes", []) if isinstance(node, dict) and _node_matches(node, concept)]


def _relation_matches(expected: str, observed: str) -> bool:
    if observed == expected:
        return True
    return expected in {"provides", "evaluates"} and observed in {"has_source", "verifies"}


def generate_prediction_paths(workspace: dict[str, Any]) -> dict[str, Any]:
    ensure_cortex_dirs()
    expected_paths: list[dict[str, Any]] = []
    for pattern in CANONICAL_EXPECTATIONS:
        sources = _find_nodes(workspace, pattern["source_concept"])
        targets = _find_nodes(workspace, pattern["target_concept"])
        if not sources or not targets:
            expected_paths.append({**pattern, "expected": True, "materializable": False, "reason": "concept_missing"})
            continue
        expected_paths.append(
            {
                **pattern,
                "expected": True,
                "materializable": True,
                "source": sources[0]["node_id"],
                "target": targets[0]["node_id"],
            }
        )
    result = {
        "prediction_run_id": f"pred_{hashlib.sha256(str(expected_paths).encode('utf-8')).hexdigest()[:18]}",
        "query": workspace.get("query", ""),
        "expected_paths": expected_paths,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
    return result


def compare_predictions_to_evidence(predictions: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    ensure_cortex_dirs()
    edges = [edge for edge in workspace.get("active_edges", []) if isinstance(edge, dict)]
    observed_paths: list[dict[str, Any]] = []
    prediction_errors: list[dict[str, Any]] = []
    strengthened: list[dict[str, Any]] = []
    weakened: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for expected in predictions.get("expected_paths", []):
        if not isinstance(expected, dict):
            continue
        if not expected.get("materializable"):
            error = {**expected, "prediction_error": 0.72, "error_reason": expected.get("reason") or "not_materializable"}
            prediction_errors.append(error)
            unverified.append(error)
            continue
        source = str(expected.get("source"))
        target = str(expected.get("target"))
        relation = str(expected.get("relation"))
        match = next(
            (
                edge for edge in edges
                if (
                    str(edge.get("source")) == source
                    and str(edge.get("target")) == target
                    and _relation_matches(relation, str(edge.get("relation")))
                )
                or (
                    _label(edge.get("source_concept")) == _label(expected.get("source_concept"))
                    and _label(edge.get("target_concept")) == _label(expected.get("target_concept"))
                    and _relation_matches(relation, str(edge.get("relation")))
                )
            ),
            None,
        )
        if match:
            weight = bounded_float(match.get("weight"), 0.5)
            observed = {**expected, "edge_id": match.get("edge_id"), "observed": True, "prediction_error": bounded_float(1.0 - weight)}
            observed_paths.append(observed)
            strengthened.append({"edge_id": match.get("edge_id"), "relation": match.get("relation"), "plasticity_delta": round(0.05 + weight * 0.08, 4)})
        else:
            error = {**expected, "observed": False, "prediction_error": 0.64, "error_reason": "expected_path_missing"}
            prediction_errors.append(error)
            weakened.append({"source": source, "target": target, "relation": relation, "plasticity_delta": -0.04})
            unverified.append(error)
    trace = PredictionTrace(
        trace_id=_trace_id(str(workspace.get("query") or "")),
        query=str(workspace.get("query") or ""),
        expected_paths=[row for row in predictions.get("expected_paths", []) if isinstance(row, dict)],
        observed_paths=observed_paths,
        prediction_errors=prediction_errors,
        strengthened_edges=strengthened,
        weakened_edges=weakened,
        unverified_hypotheses=unverified,
    ).to_dict()
    trace["mean_prediction_error"] = round(
        sum(float(row.get("prediction_error") or 0.0) for row in prediction_errors) / max(1, len(prediction_errors) + len(observed_paths)),
        4,
    )
    trace["self_generated_truth_saved"] = False
    trace["local_brain_write"] = False
    append_jsonl(DEFAULT_CORTEX_ROOT / "prediction_traces.jsonl", {**trace, "recorded_at": now_iso()})
    return trace
