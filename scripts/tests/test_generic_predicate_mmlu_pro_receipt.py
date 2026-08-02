from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.eval_evidence.receipt import BenchmarkEvidenceError, bind_files
from scripts import generic_predicate_mmlu_pro_receipt as receipt


def _rows() -> list[dict]:
    categories = sorted(receipt.bench._MMLU_CATEGORIES)
    rows = []
    for ordinal in range(receipt.EXPECTED_ITEMS):
        rows.append(
            {
                "ordinal": ordinal,
                "q": f"Synthetic question {ordinal}?",
                "choices": {"A": f"left-{ordinal}", "B": f"right-{ordinal}"},
                "gold": "B" if ordinal == 0 else "A",
                "category": categories[ordinal % len(categories)],
            }
        )
    return rows


def _fixed_rows() -> list[dict]:
    rows, _ = receipt.mmlu._load_dataset(receipt.REPO)
    return rows


def _generic(choice: str | None = None) -> dict:
    value = receipt._empty_generic_record()
    if choice is None:
        return value
    value.update(
        {
            "eligible": True,
            "role_extracted": True,
            "context_ready": True,
            "compiled": True,
            "engine_called": True,
            "fired": True,
            "proof_verified": True,
            "grounded": True,
            "status": "proof_verified",
            "reason": "exact_proof_replayed",
            "prepared_input_digest_sha256": "1" * 64,
            "prepared_choices_digest_sha256": "2" * 64,
            "role_receipt_digest_sha256": "3" * 64,
            "context_digest_sha256": "4" * 64,
            "compiler_receipt_digest_sha256": "5" * 64,
            "proof_decision_digest_sha256": "6" * 64,
            "proof_receipt_digest_sha256": "7" * 64,
            "choice_key": choice,
        }
    )
    return value


def _condition(
    baseline: str,
    *,
    generic_choice: str | None = None,
) -> dict:
    generic = _generic(generic_choice)
    counterfactual = generic_choice if generic_choice is not None else baseline
    core = {
        "baseline_choice_key": baseline,
        "baseline_choice_digest_sha256": receipt._choice_digest(baseline),
        "baseline_mode": "guess",
        "baseline_semantic_digest_sha256": canonical_digest(
            {"choice_key": baseline, "mode": "guess"}
        ),
        "live_choice_key": baseline,
        "live_semantic_digest_sha256": canonical_digest(
            {"choice_key": baseline, "mode": "guess"}
        ),
        "counterfactual_choice_key": counterfactual,
        "counterfactual_choice_digest_sha256": receipt._choice_digest(
            counterfactual
        ),
        "counterfactual_override_applied": generic_choice is not None,
        "generic": generic,
    }
    return {
        **core,
        "condition_semantic_digest_sha256": canonical_digest(core),
    }


def _worker_payload(rows: list[dict], *, replay: bool) -> dict:
    items = []
    for ordinal, row in enumerate(rows):
        primary = ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        order = list(reversed(primary)) if replay else primary
        baseline = "A"
        generic_choice = "B" if ordinal in (0, 1) else None
        items.append(
            {
                "item_id": receipt.mmlu._item_identity(row, ordinal),
                "ordinal": ordinal,
                "execution_order": order,
                "conditions": {
                    "off": _condition(baseline),
                    "on": _condition(
                        baseline, generic_choice=generic_choice
                    ),
                },
            }
        )
    return {
        "schema_version": receipt.SCHEMA_VERSION + ".worker.v1",
        "baseline_store": "fixture-store",
        "gold_received": False,
        "items": items,
    }


def _scope(
    name: str, *, paths: tuple[str, ...] | None = None
) -> dict:
    files = [
        {"path": path, "bytes": 1, "sha256": "a" * 64}
        for path in sorted(paths or (f"fixture/{name}",))
    ]
    return {
        "files": files,
        "content_sha256": receipt._sha256(
            receipt.canonical_json_bytes(files)
        ),
    }


def _manifest(*, red_stage5: bool = True) -> dict:
    rows = _fixed_rows()
    scopes = {
        name: _scope(name)
        for name in (
            "stage",
            "baseline_store",
        )
    }
    scopes["source"] = _scope(
        "source", paths=tuple(sorted(receipt.SOURCE_PATHS))
    )
    scopes["candidate"] = _scope(
        "candidate", paths=receipt._frozen_candidate_paths()
    )
    scopes["dataset"] = bind_files(
        receipt.REPO, (receipt.DATASET_PATH, receipt.GPQA_PATH)
    )
    stage5 = {
        "path": "reports/benchmarks/stage5.json",
        "sha256": (
            receipt.EXPECTED_STAGE5_RED_SHA256
            if red_stage5
            else "b" * 64
        ),
        "schema_version": receipt.STAGE5_SCHEMA_VERSION,
        "stage5_status": (
            "red_unsealed_diagnostic" if red_stage5 else "sealed_green"
        ),
        "gate_pass": not red_stage5,
        "stage5_failures": 51 if red_stage5 else 0,
        "prerequisite_passed": not red_stage5,
        "frozen_candidate_commit": receipt.FROZEN_CANDIDATE_COMMIT,
        "candidate_source_digest_sha256": (
            receipt._stage5_frozen_candidate_contract()[0]
        ),
    }
    gpqa = {
        "status": "blocked_fail_closed",
        "dataset_path": receipt.GPQA_PATH,
        "dataset_sha256": receipt.EXPECTED_GPQA_SHA256,
        "row_count": 198,
        "malformed_row_count": 3,
        "malformed_zero_based_ordinals": [89, 126, 191],
        "reason": "duplicate_normalized_answer_text_across_labels",
        "strict_loader_rejected": True,
        "accuracy_available": False,
        "baseline_available": False,
        "lift_available": False,
    }
    return receipt._assemble_receipt(
        rows=rows,
        dataset_bytes=(receipt.REPO / receipt.DATASET_PATH).read_bytes(),
        primary=_worker_payload(rows, replay=False),
        repeated=_worker_payload(rows, replay=True),
        baseline_store="fixture-store",
        stage5=stage5,
        scopes=scopes,
        gpqa_blocker=gpqa,
    )


def test_worker_input_is_fixed_counterbalanced_and_gold_blind(
    tmp_path: Path,
) -> None:
    rows = _rows()
    primary = tmp_path / "primary.jsonl"
    replay = tmp_path / "replay.jsonl"

    receipt._write_worker_input(primary, rows, replay=False)
    receipt._write_worker_input(replay, rows, replay=True)

    primary_rows = [
        json.loads(line)
        for line in primary.read_text(encoding="utf-8").splitlines()
    ]
    replay_rows = [
        json.loads(line)
        for line in replay.read_text(encoding="utf-8").splitlines()
    ]
    assert len(primary_rows) == len(replay_rows) == 40
    assert sum(
        row["execution_order"] == ["off", "on"]
        for row in primary_rows
    ) == 20
    assert sum(
        row["execution_order"] == ["on", "off"]
        for row in primary_rows
    ) == 20
    assert all(
        replay_row["execution_order"]
        == list(reversed(primary_row["execution_order"]))
        for primary_row, replay_row in zip(primary_rows, replay_rows)
    )
    assert all("gold" not in row and "category" not in row for row in primary_rows)


def test_counterfactual_scoring_tracks_win_regression_wrong_fire_and_invariance() -> None:
    rows = _rows()
    items = receipt._score_worker_results(
        rows,
        _worker_payload(rows, replay=False),
        _worker_payload(rows, replay=True),
        baseline_store="fixture-store",
    )
    metrics = receipt._derive_metrics(items, prerequisite_passed=True)

    assert metrics["denominator"] == 40
    assert metrics["primary_order_counts"] == {
        "off_then_on": 20,
        "on_then_off": 20,
    }
    assert metrics["baseline_correct"] == 39
    assert metrics["counterfactual_on_correct"] == 39
    assert metrics["wins"] == 1
    assert metrics["regressions"] == 1
    assert metrics["generic_wrong_fires"] == 1
    assert metrics["conditions"]["off"]["compiled"] == 0
    assert metrics["conditions"]["on"]["compiled"] == 2
    assert metrics["conditions"]["on"]["fired"] == 2
    assert metrics["conditions"]["on"]["proof_verified"] == 2
    assert metrics["live_answer_invariant"] == 40
    assert metrics["semantic_replay_all"] is True
    assert metrics["measurement_integrity_passed"] is True
    assert metrics["prerequisite_passed"] is True
    assert metrics["promotion_gate_passed"] is False


def test_receipt_recomputes_and_all_authority_claims_remain_false() -> None:
    manifest = _manifest()

    assert receipt.validate_receipt(
        manifest, require_current=False
    ) == []
    assert manifest["claims"]["live_answer_authority"] is False
    assert manifest["claims"]["sealed"] is False
    assert manifest["claims"]["promotion_allowed"] is False
    assert manifest["claims"]["e4_claimed"] is False
    assert manifest["claims"]["e5_claimed"] is False
    assert manifest["claims"]["benchmark_capability_claimed"] is False
    assert manifest["claims"]["gpqa_accuracy_claimed"] is False
    assert (
        manifest["claims"]["gold_filesystem_isolation_established"]
        is False
    )
    assert (
        manifest["claims"]["independent_proof_reverification_available"]
        is False
    )
    assert (
        manifest["claims"]["independent_replay_reverification_available"]
        is False
    )
    assert (
        manifest["integrity"]["generic_async_submit_used_for_scoring"]
        is False
    )
    assert manifest["integrity"]["gold_filesystem_isolation_enforced"] is False
    assert manifest["integrity"]["proof_payload_embedded"] is False
    assert manifest["integrity"]["replay_payload_embedded"] is False

    tampered = json.loads(json.dumps(manifest))
    tampered["items"][0]["outcomes"]["baseline_correct"] = not tampered[
        "items"
    ][0]["outcomes"]["baseline_correct"]
    tampered["metrics"] = receipt._derive_metrics(
        tampered["items"], prerequisite_passed=False
    )
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
    assert any(
        "outcomes do not rescore" in finding
        for finding in receipt.validate_receipt(
            tampered, require_current=False
        )
    )


def test_historical_scope_requires_sorted_unique_recomputed_inventory() -> None:
    manifest = _manifest()
    tampered = json.loads(json.dumps(manifest))
    tampered["source"]["files"] = list(
        reversed(tampered["source"]["files"])
    )
    tampered["source"]["content_sha256"] = receipt._sha256(
        receipt.canonical_json_bytes(tampered["source"]["files"])
    )
    tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)

    assert "source scope shape mismatch" in receipt.validate_receipt(
        tampered, require_current=False
    )


def test_historical_source_and_candidate_inventories_are_exact() -> None:
    manifest = _manifest()
    for scope_name, expected_finding in (
        ("source", "source inventory mismatch"),
        ("candidate", "candidate inventory mismatch"),
    ):
        tampered = json.loads(json.dumps(manifest))
        tampered[scope_name]["files"].pop()
        tampered[scope_name]["content_sha256"] = receipt._sha256(
            receipt.canonical_json_bytes(
                tampered[scope_name]["files"]
            )
        )
        tampered["manifest_checksum_sha256"] = receipt._checksum(tampered)
        assert expected_finding in receipt.validate_receipt(
            tampered, require_current=False
        )


def test_worker_root_schema_and_baseline_store_are_exact() -> None:
    rows = _rows()
    primary = _worker_payload(rows, replay=False)
    replay = _worker_payload(rows, replay=True)
    primary["baseline_store"] = "wrong-store"

    with pytest.raises(
        BenchmarkEvidenceError, match="root schema mismatch"
    ):
        receipt._score_worker_results(
            rows,
            primary,
            replay,
            baseline_store="fixture-store",
        )

    primary = _worker_payload(rows, replay=False)
    primary["unexpected"] = True
    with pytest.raises(
        BenchmarkEvidenceError, match="root schema mismatch"
    ):
        receipt._score_worker_results(
            rows,
            primary,
            replay,
            baseline_store="fixture-store",
        )


def test_worker_subprocess_timeout_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args, **kwargs):
        raise receipt.subprocess.TimeoutExpired(
            cmd="fixture-worker",
            timeout=receipt.WORKER_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(receipt.subprocess, "run", timeout)
    with pytest.raises(
        BenchmarkEvidenceError, match="worker failed closed"
    ):
        receipt._run_worker(
            tmp_path / "input.jsonl",
            tmp_path / "output.json",
            baseline_store="fixture-store",
        )


def test_e4_source_and_transitive_candidate_controllers_are_bound() -> None:
    manifest = _manifest()
    source_paths = {
        row["path"] for row in manifest["source"]["files"]
    }
    candidate_paths = {
        row["path"] for row in manifest["candidate"]["files"]
    }

    assert "scripts/science_stage_e4_receipt.py" in source_paths
    assert candidate_paths == set(receipt._frozen_candidate_paths())
    assert set(receipt.REQUIRED_CANDIDATE_BINDINGS).issubset(candidate_paths)


def test_candidate_census_is_independent_of_mutable_e4_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = receipt._frozen_candidate_paths()
    monkeypatch.setattr(receipt.mmlu, "CANDIDATE_PATHS", ())
    monkeypatch.setattr(receipt.mmlu.e4, "CANDIDATE_PATHS", ())
    assert receipt._frozen_candidate_paths() == before


def test_claim_classification_and_entire_protocol_are_canonical() -> None:
    manifest = _manifest()
    tampered_claim = json.loads(json.dumps(manifest))
    tampered_claim["claims"]["classification"] = "sealed_e5_promotable"
    tampered_claim["manifest_checksum_sha256"] = receipt._checksum(
        tampered_claim
    )
    assert "claims mismatch" in receipt.validate_receipt(
        tampered_claim, require_current=False
    )

    for mutate in (
        lambda protocol: protocol.pop("promotion_rule"),
        lambda protocol: protocol["limitations"].pop(),
    ):
        tampered_protocol = json.loads(json.dumps(manifest))
        mutate(tampered_protocol["protocol"])
        tampered_protocol["manifest_checksum_sha256"] = receipt._checksum(
            tampered_protocol
        )
        assert "protocol mismatch" in receipt.validate_receipt(
            tampered_protocol, require_current=False
        )


def test_minimal_stage5_green_json_is_rejected() -> None:
    minimal = {
        "schema_version": receipt.STAGE5_SCHEMA_VERSION,
        "gate_pass": True,
        "failures": [],
        "authority_disclaimer": {
            "external_evaluation": False,
            "external_authenticity": False,
            "independent_evaluation": False,
            "e4": False,
            "e5": False,
            "capability_claim": False,
        },
        "frozen_candidate": {
            "commit": receipt.FROZEN_CANDIDATE_COMMIT,
            "candidate_source_digest_sha256": "d" * 64,
        },
    }
    with pytest.raises(
        BenchmarkEvidenceError, match="root schema is invalid"
    ):
        receipt._validate_stage5_document(
            minimal, repo_root=receipt.REPO
        )
    assert receipt.TRUSTED_STAGE5_GREEN_SHA256 == frozenset()


def test_structurally_accepted_green_still_requires_known_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "green.json"
    value = {
        "schema_version": receipt.STAGE5_SCHEMA_VERSION,
        "gate_pass": True,
        "failures": [],
        "authority_disclaimer": {
            "external_evaluation": False,
            "external_authenticity": False,
            "independent_evaluation": False,
            "e4": False,
            "e5": False,
            "capability_claim": False,
        },
        "frozen_candidate": {
            "commit": receipt.FROZEN_CANDIDATE_COMMIT,
            "candidate_source_digest_sha256": "d" * 64,
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(
        receipt,
        "_validate_stage5_document",
        lambda value, repo_root: None,
    )

    with pytest.raises(
        BenchmarkEvidenceError,
        match="green receipt digest is not explicitly trusted",
    ):
        receipt._read_stage5_prerequisite(path, repo_root=tmp_path)


def test_default_rejects_and_explicit_diagnostic_accepts_pinned_red() -> None:
    path = (
        receipt.REPO
        / "reports/benchmarks/atanor_a2_stage5_fresh_holdout_v1.json"
    )
    with pytest.raises(
        BenchmarkEvidenceError, match="prerequisite is not sealed"
    ):
        receipt._read_stage5_prerequisite(path)

    bound = receipt._read_stage5_prerequisite(
        path,
        allow_red_diagnostic=True,
    )
    assert bound["stage5_status"] == "red_unsealed_diagnostic"
    assert bound["gate_pass"] is False
    assert bound["stage5_failures"] == 51
    assert bound["prerequisite_passed"] is False
    assert bound["sha256"] == receipt.EXPECTED_STAGE5_RED_SHA256


def test_red_diagnostic_receipt_separates_integrity_from_prerequisite() -> None:
    manifest = _manifest(red_stage5=True)

    assert receipt.validate_receipt(
        manifest, require_current=False
    ) == []
    assert (
        manifest["stage5_prerequisite"]["stage5_status"]
        == "red_unsealed_diagnostic"
    )
    assert manifest["metrics"]["measurement_integrity_passed"] is True
    assert manifest["metrics"]["prerequisite_passed"] is False
    assert manifest["metrics"]["promotion_gate_passed"] is False
    assert manifest["integrity"]["stage5_gate_bound"] is False
    assert manifest["integrity"]["stage5_red_diagnostic_explicit"] is True
    assert manifest["claims"]["promotion_allowed"] is False
    assert manifest["claims"]["e4_claimed"] is False
    assert manifest["claims"]["e5_claimed"] is False
    assert manifest["claims"]["benchmark_capability_claimed"] is False
    assert manifest["claims"]["live_answer_authority"] is False

    inconsistent = json.loads(json.dumps(manifest))
    inconsistent["integrity"]["stage5_gate_bound"] = True
    inconsistent["manifest_checksum_sha256"] = receipt._checksum(inconsistent)
    assert "integrity mismatch" in receipt.validate_receipt(
        inconsistent, require_current=False
    )


def test_gpqa_is_aggregate_only_and_accuracy_stays_blocked() -> None:
    blocker = receipt._gpqa_blocker()

    assert blocker == {
        "status": "blocked_fail_closed",
        "dataset_path": receipt.GPQA_PATH,
        "dataset_sha256": receipt.EXPECTED_GPQA_SHA256,
        "row_count": 198,
        "malformed_row_count": 3,
        "malformed_zero_based_ordinals": [89, 126, 191],
        "reason": "duplicate_normalized_answer_text_across_labels",
        "strict_loader_rejected": True,
        "accuracy_available": False,
        "baseline_available": False,
        "lift_available": False,
    }
    assert not any(
        key in blocker for key in ("question", "choices", "answer_text")
    )


def test_validate_cli_accepts_structural_historical_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(receipt.canonical_json_bytes(_manifest()) + b"\n")

    assert receipt._main(["validate", str(path), "--historical"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"findings": [], "valid": True}


def test_build_cli_refuses_missing_stage5_before_any_benchmark(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing-stage5.json"
    output = tmp_path / "never-written.json"

    assert (
        receipt._main(
            [
                "build",
                "--stage5-seal",
                str(missing),
                "--baseline-store",
                "fixture-store",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "BenchmarkEvidenceError"
