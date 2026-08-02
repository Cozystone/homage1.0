from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from packages.cognitive_core.canonical import canonical_json
from packages.reasoning_vm.science_candidate import (
    ScienceStageBundle,
    answer_science_candidate,
)
from packages.reasoning_vm.science_quantity_staging import (
    load_science_quantity_stage,
)
from packages.reasoning_vm.science_staging import load_science_stage
from packages.reasoning_vm.deliberator.science_relation_staging import (
    load_science_relation_stage,
)


REPO = Path(__file__).resolve().parents[2]
REPORT = (
    REPO
    / "scripts/tests/fixtures/science_relation_sibling_curve_v1.json"
)
DATASET = REPO / "data/benchmarks/mmlu_pro/slice_5.jsonl"
STAGE_FIXTURES = REPO / "packages/reasoning_vm/tests/fixtures"
EXPECTED_REPORT_SHA256 = (
    "815025ce90b897d212182affdfee01f6af2c6733115e7c503f6c60f211e83038"
)
EXPECTED_DATASET_SHA256 = (
    "a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36"
)
RELATION_STEM = "Which country is Athens located in?"
RELATION_CHOICES = {
    "A": "France",
    "B": "Greece",
    "C": "Italy",
}


def _load_rows() -> tuple[bytes, list[dict[str, Any]]]:
    payload = DATASET.read_bytes()
    rows = [
        json.loads(line)
        for line in payload.decode("utf-8").splitlines()
    ]
    assert len(rows) == 40
    return payload, rows


def _run(
    rows: list[dict[str, Any]],
    bundle: ScienceStageBundle,
) -> list[dict[str, Any]]:
    outputs = []
    for row in rows:
        outputs.append(
            answer_science_candidate(
                row["question"],
                row["choices"],
                bundle,
                base_facts=lambda _subject: [],
                base_state_digest=lambda: "frozen-base-state",
            )
        )
    return outputs


def _metrics(
    rows: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> dict[str, int]:
    answered = [
        (row, output)
        for row, output in zip(rows, outputs, strict=True)
        if output["choice_key"] is not None
    ]
    return {
        "answered": len(answered),
        "answered_correct": sum(
            output["choice_key"] == row["gold"]
            for row, output in answered
        ),
        "errors": sum(output["mode"] == "error" for output in outputs),
        "grounded": sum(
            output["mode"] == "grounded" for output in outputs
        ),
        "relation_invoked": sum(
            output["lane"]["relation_invoked"] for output in outputs
        ),
        "relation_selected": sum(
            output["lane"]["selected"] == "relation"
            for output in outputs
        ),
        "scalar_selected": sum(
            output["lane"]["selected"] == "scalar"
            for output in outputs
        ),
        "strict_correct": sum(
            output["choice_key"] == row["gold"]
            for row, output in zip(rows, outputs, strict=True)
        ),
        "total": len(outputs),
        "unsupported": sum(
            output["route"]["decision"]["status"] == "unsupported"
            for output in outputs
        ),
    }


def test_frozen_exposed_curve_replays_exactly() -> None:
    report_bytes = REPORT.read_bytes()
    report = json.loads(report_bytes)
    dataset_bytes, rows = _load_rows()

    assert report_bytes == canonical_json(report).encode("utf-8") + b"\n"
    assert hashlib.sha256(report_bytes).hexdigest() == (
        EXPECTED_REPORT_SHA256
    )
    assert hashlib.sha256(dataset_bytes).hexdigest() == (
        EXPECTED_DATASET_SHA256
    )
    assert len(dataset_bytes) == 31014

    atomic = load_science_stage(
        STAGE_FIXTURES / "science_stage_atomic_number_v1"
    )
    scalar = load_science_quantity_stage(
        STAGE_FIXTURES / "science_stage_scalar_quantity_v1"
    )
    relation = load_science_relation_stage(
        STAGE_FIXTURES / "science_stage_typed_relation_v1"
    )
    as_outputs = _run(
        rows,
        ScienceStageBundle(
            atomic_stage=atomic,
            scalar_stage=scalar,
        ),
    )
    asr_outputs = _run(
        rows,
        ScienceStageBundle(
            atomic_stage=atomic,
            scalar_stage=scalar,
            relation_stage=relation,
        ),
    )

    off = answer_science_candidate(
        RELATION_STEM,
        RELATION_CHOICES,
        ScienceStageBundle(),
    )
    on = answer_science_candidate(
        RELATION_STEM,
        RELATION_CHOICES,
        ScienceStageBundle(relation_stage=relation),
    )

    expected = {
        "additive_preservation": {
            "core_outcome_equal_count": sum(
                tuple(left[key] for key in ("choice_key", "mode", "reason"))
                == tuple(
                    right[key] for key in ("choice_key", "mode", "reason")
                )
                for left, right in zip(
                    as_outputs,
                    asr_outputs,
                    strict=True,
                )
            ),
            "lane_outcome_equal_count": sum(
                left["lane_outcome"] == right["lane_outcome"]
                for left, right in zip(
                    as_outputs,
                    asr_outputs,
                    strict=True,
                )
            ),
            "route_equal_count": sum(
                left["route"] == right["route"]
                for left, right in zip(
                    as_outputs,
                    asr_outputs,
                    strict=True,
                )
            ),
            "total": 40,
        },
        "claims": {
            "canonical_e4_established": False,
            "capability_improvement_established": False,
            "e5_established": False,
            "independent_evaluation_established": False,
            "public_reach_increased": False,
        },
        "conditions": {
            "AS": {
                "bundle": "atomic_scalar",
                "metrics": _metrics(rows, as_outputs),
            },
            "ASR": {
                "bundle": "atomic_scalar_relation",
                "metrics": _metrics(rows, asr_outputs),
            },
        },
        "deltas": {
            "answered": 0,
            "relation_invoked": 0,
            "relation_selected": 0,
            "strict_correct": 0,
        },
        "diagnostic_control": {
            "off": {
                "accepted_fire": off["lane_outcome"]["engine"][
                    "accepted_fire"
                ],
                "choice_key": off["choice_key"],
                "compiled": off["lane_outcome"]["compiler"]["compiled"],
                "mode": off["mode"],
                "relation_invoked": off["lane"]["relation_invoked"],
            },
            "on": {
                "accepted_fire": on["lane_outcome"]["engine"][
                    "accepted_fire"
                ],
                "choice_key": on["choice_key"],
                "compiled": on["lane_outcome"]["compiler"]["compiled"],
                "mode": on["mode"],
                "proof_candidate_count": on["lane_outcome"]["staging"][
                    "proof_candidate_count"
                ],
                "relation_invoked": on["lane"]["relation_invoked"],
                "source_property_id": on["lane_outcome"]["staging"][
                    "source_property_id"
                ],
            },
        },
        "evidence_kind": (
            "evaluator_only_exposed_additive_preservation_curve"
        ),
        "interpretation": (
            "The diagnostic sibling lane is wired and proof-carrying, but "
            "it reaches zero items on the frozen public slice and "
            "establishes no capability lift."
        ),
        "schema_version": "atanor.science-relation-sibling-curve.v1",
        "scope": {
            "dataset_bytes": 31014,
            "dataset_path": "data/benchmarks/mmlu_pro/slice_5.jsonl",
            "dataset_sha256": EXPECTED_DATASET_SHA256,
            "public_exposed": True,
            "row_count": 40,
        },
    }

    assert report == expected
    assert all(
        output["integrity"]["gold_in_candidate_payload"] is False
        for output in as_outputs + asr_outputs + [off, on]
    )
