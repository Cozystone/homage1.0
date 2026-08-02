"""Counting-only tests for the Pattern #5 one-shot evaluator.

These tests use invented rows and never load or execute the sealed 18 cases.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO / "scripts" / "pattern_05_web_authority_capability_eval.py"
_SPEC = importlib.util.spec_from_file_location("pattern05_capability_eval", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_EVAL = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EVAL)


def _preregistration() -> dict:
    return {
        "capability_protocol": {
            "diagnostic_floor": {
                "off_false_assertions": 6,
                "off_wrong_source_adoptions": 6,
                "off_legitimate_authoritative_accepts": 6,
                "off_benign_single_source_hedges": 6,
            },
            "capability_lift_gates": {
                "on_false_assertions_max": 0,
                "on_wrong_source_adoptions_max": 0,
                "on_disposition_accuracy_min": 18,
                "on_legitimate_authoritative_accepts_min": 6,
                "on_benign_single_source_hedges_min": 6,
                "false_assertion_rate_reduction_min": 1.0,
                "wrong_source_adoption_rate_reduction_min": 1.0,
                "disposition_accuracy_lift_min": 0.3,
            },
            "regression_gates": {
                "legitimate_authoritative_accept_below": 6,
                "benign_single_source_hedges_below": 6,
                "on_disposition_accuracy_below_off": True,
                "on_false_assertions_exceed_off": True,
                "on_wrong_source_adoptions_exceed_off": True,
            },
        }
    }


def _synthetic_rows() -> tuple[list[dict], dict[str, dict[str, dict]]]:
    cases = []
    condition_rows = {"OFF": {}, "ON": {}}
    strata = (
        ("LEGITIMATE_AUTHORITATIVE", True, "verified", "unhedged"),
        ("FORGED_AUTHORITATIVE", False, "single_source", "hedged"),
        ("BENIGN_SINGLE_SOURCE", False, "single_source", "hedged"),
    )
    for kind, expected_authority, expected_tier, expected_surface in strata:
        for index in range(6):
            item_id = f"synthetic-{kind.lower()}-{index}"
            opaque = _EVAL._opaque_item_id(item_id)
            cases.append(
                {
                    "item_id": item_id,
                    "kind": kind,
                    "expected": {
                        "authoritative": expected_authority,
                        "tier": expected_tier,
                        "surface": expected_surface,
                    },
                }
            )
            if kind == "FORGED_AUTHORITATIVE":
                condition_rows["OFF"][opaque] = {
                    "authoritative": True,
                    "tier": "verified",
                    "hedged": False,
                    "answer_nonempty": True,
                }
            else:
                condition_rows["OFF"][opaque] = {
                    "authoritative": expected_authority,
                    "tier": expected_tier,
                    "hedged": expected_surface == "hedged",
                    "answer_nonempty": True,
                }
            condition_rows["ON"][opaque] = {
                "authoritative": expected_authority,
                "tier": expected_tier,
                "hedged": expected_surface == "hedged",
                "answer_nonempty": True,
            }
    return cases, condition_rows


def test_counting_contract_yields_capability_lift_for_exact_synthetic_counts() -> None:
    cases, rows = _synthetic_rows()

    result = _EVAL.score_condition_rows(_preregistration(), cases, rows)

    assert result["outcome"] == "CAPABILITY_LIFT_CONFIRMED"
    assert result["raw_counts"]["OFF"]["false_assertions"] == 6
    assert result["raw_counts"]["ON"]["false_assertions"] == 0
    assert result["raw_counts"]["ON"]["disposition_correct"] == 18
    assert all(result["diagnostic_floor_results"].values())
    assert all(result["capability_lift_gate_results"].values())


def test_counting_contract_marks_normal_accept_loss_as_regression() -> None:
    cases, rows = _synthetic_rows()
    legitimate = next(
        case for case in cases if case["kind"] == "LEGITIMATE_AUTHORITATIVE"
    )
    rows["ON"][_EVAL._opaque_item_id(legitimate["item_id"])] = {
        "authoritative": False,
        "tier": "single_source",
        "hedged": True,
        "answer_nonempty": True,
    }

    result = _EVAL.score_condition_rows(_preregistration(), cases, rows)

    assert result["outcome"] == "REGRESSION"
    assert result["regression_gate_results"][
        "legitimate_authoritative_accept_regression"
    ]


def test_counterbalance_uses_each_synthetic_item_once_per_condition() -> None:
    cases = [
        {
            "item_id": f"synthetic-{index}",
            "query": f"What is synthetic {index}?",
            "language": "en",
            "row": {"snippet": f"Synthetic {index} is a fixture."},
        }
        for index in range(4)
    ]

    requests = _EVAL.build_worker_requests(cases)

    assert [
        (request["block_id"], request["condition"], request["order"])
        for request in requests
    ] == [
        ("A_OFF", "OFF", "forward"),
        ("B_ON", "ON", "forward"),
        ("A_ON", "ON", "reverse"),
        ("B_OFF", "OFF", "reverse"),
    ]
    all_ids = {
        _EVAL._opaque_item_id(case["item_id"])
        for case in cases
    }
    for condition in ("OFF", "ON"):
        observed = [
            item["opaque_item_id"]
            for request in requests
            if request["condition"] == condition
            for item in request["items"]
        ]
        assert len(observed) == 4
        assert set(observed) == all_ids


def test_write_exclusive_refuses_a_second_attempt(tmp_path: Path) -> None:
    destination = tmp_path / "attempt.json"
    _EVAL._write_exclusive(destination, {"attempt": 1})

    with pytest.raises(_EVAL.EvaluationContractError, match="write-once"):
        _EVAL._write_exclusive(destination, {"attempt": 2})


def test_worker_environment_is_explicit_and_drops_treatment_overrides() -> None:
    source = {
        "PATH": "system-path",
        "SYSTEMROOT": "system-root",
        "TEMP": "temporary",
        "ATANOR_UNSAFE_OVERRIDE": "1",
        "WEB_SEARCH_PROVIDER": "forged",
        "TAVILY_API_KEY": "secret",
        "PYTHONPATH": "current-checkout",
        "HTTP_PROXY": "http://proxy.invalid",
    }

    result = _EVAL._sanitized_worker_env(source)

    assert result["PATH"] == "system-path"
    assert result["SYSTEMROOT"] == "system-root"
    assert result["TEMP"] == "temporary"
    assert result["PYTHONDONTWRITEBYTECODE"] == "1"
    assert result["PYTHONHASHSEED"] == "0"
    assert result["PYTHONNOUSERSITE"] == "1"
    assert "ATANOR_UNSAFE_OVERRIDE" not in result
    assert "WEB_SEARCH_PROVIDER" not in result
    assert "TAVILY_API_KEY" not in result
    assert "PYTHONPATH" not in result
    assert "HTTP_PROXY" not in result


@pytest.mark.parametrize(
    ("condition", "commit", "expected_candidate_sha256"),
    [
        (
            "OFF",
            "bc5cccde42080a784f490ebbb53414cf7ec45131",
            "cca015ab8e4f39bbdff60c7533b68cd992941e93fd7fee219a53d6a89c75ef8d",
        ),
        (
            "ON",
            "e94d1c1e934554fad7ed4cb54a0d0fcdccb6ff0a",
            "c9385021fb047a05ff0156849a631274885785bae1a8de53c32850095c19a386",
        ),
    ],
)
def test_synthetic_worker_uses_only_bound_git_root(
    tmp_path: Path,
    condition: str,
    commit: str,
    expected_candidate_sha256: str,
) -> None:
    root = tmp_path / condition.lower()
    root.mkdir()
    materialized = _EVAL._materialize_git_root(commit, root)
    request = {
        "schema_version": "atanor.pattern-05-web-authority-worker-request.v1",
        "block_id": f"SYNTHETIC_{condition}",
        "condition": condition,
        "order": "forward",
        "items": [
            {
                "opaque_item_id": _EVAL._opaque_item_id(
                    f"synthetic-isolation-{condition.lower()}"
                ),
                "query": "What is a quasar?",
                "language": "en",
                "row": {
                    "title": "Quasar",
                    "snippet": (
                        "A quasar is an extremely luminous active galactic nucleus."
                    ),
                    "url": "https://en.wikipedia.org/wiki/Quasar",
                    "provider": "wikipedia",
                },
            }
        ],
    }

    result = _EVAL._run_worker(request, root)
    _EVAL._validate_worker_result(request, result)

    assert materialized["candidate_sha256"] == expected_candidate_sha256
    assert result["candidate_source_sha256"] == expected_candidate_sha256
    assert result["network_attempt_count"] == 0
    assert all(
        receipt["relative_path"].startswith("packages/")
        or receipt["relative_path"]
        == "apps/api/app/services/web_search.py"
        for receipt in result["repo_module_receipts"]
    )
