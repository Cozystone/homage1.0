from __future__ import annotations

import copy
from dataclasses import dataclass
import gzip
import hashlib
from pathlib import Path
import tarfile

import pytest

from scripts import gwip_capability_eval as evaluator
from scripts import gwip_mechanism_eval as mechanism
from scripts.gwip_capability_episode_runner import (
    CandidateEpisodeRunner,
    census_runtime_dependency_sources,
    materialized_runtime_dependencies,
    ThreadSafeEvidenceSink,
)
from scripts.gwip_capability_harness import (
    JITRunLeaseIssuer,
    WORKER_REQUEST_SCHEMA,
    canonical_digest,
)
from scripts.gwip_capability_semantics import canonical_empty_memory


@dataclass(frozen=True)
class _Episode:
    start_ref: str = "fixture-state-0"
    goal_ref: str = "fixture-state-2"
    optimal_steps: int = 2


class _Environment:
    episodes = (_Episode(),)
    actions = (
        type("_Action", (), {"action_ref": "fixture-step"})(),
    )

    @staticmethod
    def public_actions() -> tuple[dict, ...]:
        return (
            {"action_id": "fixture-step", "payload": {"cue": "opaque"}},
        )

    @staticmethod
    def observation(state_ref: str, *, goal_ref: str) -> dict:
        return {
            "schema_version": "fixture-p7",
            "state_ref": state_ref,
            "features": {"value": int(state_ref.rsplit("-", 1)[1])},
            "terminal": state_ref == goal_ref,
        }

    @staticmethod
    def transition(state_ref: str, action_id: str) -> str:
        assert action_id == "fixture-step"
        value = int(state_ref.rsplit("-", 1)[1])
        return f"fixture-state-{(value + 1) % 7}"


def test_parent_environment_denies_budget_before_mutation() -> None:
    environment = evaluator.EvaluatorCapabilityEnvironment(
        _Environment(),
        episode_index=0,
    )
    assert environment.reset(0) == {"reset": True}
    for _index in range(24):
        environment.step("fixture-step")
    state_before = environment.current_state_ref
    log_before = environment.call_log
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="before environment mutation",
    ):
        environment.step("fixture-step")
    assert environment.current_state_ref == state_before
    assert environment.call_log == log_before


def test_deterministic_gzip_round_trip(tmp_path: Path) -> None:
    value = {"schema_version": "fixture.v1", "rows": [{"x": 1}]}
    first = evaluator._gzip_json_bytes(value)
    second = evaluator._gzip_json_bytes(value)
    assert first == second
    path = tmp_path / "raw.json.gz"
    path.write_bytes(first)
    assert evaluator._read_gzip_json(path, label="fixture") == value


def test_control_call_order_accepts_stop_after_terminal_step() -> None:
    log = [
        {"operation": "reset"},
        {"operation": "observe"},
        {"operation": "valid_actions"},
        {
            "operation": "step",
            "step_index": 0,
            "result": {"terminal": True, "success": True},
        },
        {"operation": "stop"},
    ]
    assert evaluator.audit_call_order(log) == {
        "passed": True,
        "findings": [],
        "executed_steps": 1,
        "stop_count": 1,
    }


def test_preregistration_is_bound_to_independent_p_blob() -> None:
    binding = evaluator._sealed_preregistration_binding(
        comparison_commit="HEAD"
    )
    assert binding["commit"] == evaluator.PREREG_COMMIT
    assert binding["validated_pair_count"] == 64
    assert {
        row["path"] for row in binding["files"]
    } == set(evaluator.PREREG_SEALED_PATHS)


def test_v3_machine_contract_and_all_episode_inputs_equal_v1() -> None:
    assert evaluator._raw_file_sha256(
        evaluator.REPO / evaluator.V3_PREREG_RELATIVE_PATH
    ) == evaluator.V3_V1_ARTIFACT_SHA256[
        evaluator.V1_PREREG_RELATIVE_PATH
    ]
    binding = evaluator._v3_dataset_binding()
    assert binding["pair_count"] == 64
    assert binding["candidate_episode_count"] == 1024
    assert binding["private_cohort_sha256"] == (
        evaluator.V3_PRIVATE_COHORT_SHA256
    )
    assert binding["all_episode_input_digests_equal_v1"] is True
    assert binding["metric_thresholds_equal_v1"] is True


def test_v3_profile_uses_distinct_paths_and_restores_v1() -> None:
    original = {
        "seed": evaluator.SEED_RELATIVE_PATH,
        "schedule": evaluator.SCHEDULE_RELATIVE_PATH,
        "attempt": evaluator.ATTEMPT_RELATIVE_PATH,
        "raw": evaluator.RAW_RELATIVE_PATH,
        "receipt": evaluator.RECEIPT_RELATIVE_PATH,
        "authority": evaluator.AUTHORITY_RELATIVE_PATH,
        "prereg": evaluator.PREREG_RELATIVE_PATH,
    }
    with evaluator._v3_run_profile():
        assert evaluator._ACTIVE_RUN_PROFILE == "v3"
        assert evaluator.SEED_RELATIVE_PATH == (
            evaluator.V3_SEED_RELATIVE_PATH
        )
        assert evaluator.SCHEDULE_RELATIVE_PATH == (
            evaluator.V3_SCHEDULE_RELATIVE_PATH
        )
        assert evaluator.ATTEMPT_RELATIVE_PATH == (
            evaluator.V3_ATTEMPT_RELATIVE_PATH
        )
        assert evaluator.RAW_RELATIVE_PATH == (
            evaluator.V3_RAW_RELATIVE_PATH
        )
        assert evaluator.RECEIPT_RELATIVE_PATH == (
            evaluator.V3_RECEIPT_RELATIVE_PATH
        )
        assert evaluator.AUTHORITY_RELATIVE_PATH == (
            evaluator.V3_AUTHORITY_RELATIVE_PATH
        )
        assert evaluator.PREREG_RELATIVE_PATH == (
            evaluator.V3_PREREG_RELATIVE_PATH
        )
        assert evaluator.V1_SEED_RELATIVE_PATH == original["seed"]
    assert evaluator._ACTIVE_RUN_PROFILE == "v1"
    assert evaluator.SEED_RELATIVE_PATH == original["seed"]
    assert evaluator.SCHEDULE_RELATIVE_PATH == original["schedule"]
    assert evaluator.ATTEMPT_RELATIVE_PATH == original["attempt"]
    assert evaluator.RAW_RELATIVE_PATH == original["raw"]
    assert evaluator.RECEIPT_RELATIVE_PATH == original["receipt"]
    assert evaluator.AUTHORITY_RELATIVE_PATH == original["authority"]
    assert evaluator.PREREG_RELATIVE_PATH == original["prereg"]


def test_v3_schedule_allows_only_operational_witness_deltas() -> None:
    v1 = evaluator._strict_json_bytes(
        (
            evaluator.REPO
            / evaluator.V1_SCHEDULE_RELATIVE_PATH
        ).read_bytes(),
        label="v1 schedule fixture",
    )
    v3 = copy.deepcopy(v1)
    for index, row in enumerate(v3["rows"]):
        row["lease_id"] = f"v3-fresh-lease-{index:04d}"
        row["nonce"] = f"v3-fresh-nonce-{index:04d}"
        row["boundary_config_path"] = f"C:/external/v3/{index}"
        row["live_context"] = {"v3": index}
    assert len(evaluator._v3_validate_prepared_schedule(v3)) == 64

    forged = copy.deepcopy(v3)
    forged["rows"][0]["episode_input_sha256"] = "0" * 64
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="changed dataset semantics",
    ):
        evaluator._v3_validate_prepared_schedule(forged)


def test_v3_lineage_binds_attempt_source_and_v3_paths() -> None:
    source = {
        "schema_version": "atanor.gwip-capability-source-binding.v1",
        "candidate_commit": evaluator.CANDIDATE_COMMIT,
        "candidate_source_sha256": (
            evaluator.V3_CANDIDATE_SOURCE_SHA256
        ),
        "evaluator_commit": "e" * 40,
        "evaluator_source_sha256": "e" * 64,
        "seed_manifest_sha256": "s" * 64,
    }
    base = evaluator._v3_verification_lineage_base()
    base["evaluator_source_binding"] = copy.deepcopy(source)
    base["v3_evaluator_commit"] = source["evaluator_commit"]
    base["v3_evaluator_source_sha256"] = source[
        "evaluator_source_sha256"
    ]
    base["dataset_binding"]["v3_schedule_semantics_equal_v1"] = True
    base["dataset_binding"][
        "v3_schedule_semantic_binding_sha256"
    ] = "d" * 64
    base["checksum_sha256"] = evaluator._v3_lineage_checksum(base)
    lineage = evaluator._finalize_v3_verification_lineage(
        base,
        fail_closed=True,
    )
    raw = {
        "verification_lineage": lineage,
        "source_binding": source,
        "preregistration_binding": {
            "files": [
                {"path": evaluator.V3_PREREG_RELATIVE_PATH},
                {"path": evaluator.V3_PREREG_DOC_RELATIVE_PATH},
            ]
        },
        "seed_manifest_binding": {
            "path": evaluator.V3_SEED_RELATIVE_PATH
        },
        "schedule_binding": {
            "path": evaluator.V3_SCHEDULE_RELATIVE_PATH
        },
        "attempt_binding": {
            "path": evaluator.V3_ATTEMPT_RELATIVE_PATH,
            "payload": {
                "verification_lineage_sha256": base[
                    "checksum_sha256"
                ]
            },
        },
        "authority_archive_binding": {
            "path": evaluator.V3_AUTHORITY_RELATIVE_PATH
        },
    }
    checked = evaluator._receipt_verification_lineage(
        raw,
        require_preserved=True,
    )
    assert checked == lineage
    assert checked["checksum_sha256"] == (
        evaluator._v3_lineage_checksum(checked)
    )
    assert checked["pre_attempt_lineage_sha256"] == (
        base["checksum_sha256"]
    )
    forged = copy.deepcopy(raw)
    forged["verification_lineage"]["v1_artifacts_preserved"] = False
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="checksum/identity",
    ):
        evaluator._receipt_verification_lineage(
            forged,
            require_preserved=True,
        )
    forged_source = copy.deepcopy(raw)
    forged_source["source_binding"]["evaluator_commit"] = "f" * 40
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="lineage/source/attempt",
    ):
        evaluator._receipt_verification_lineage(
            forged_source,
            require_preserved=True,
        )
    forged_path = copy.deepcopy(raw)
    forged_path["schedule_binding"]["path"] = (
        evaluator.V1_SCHEDULE_RELATIVE_PATH
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="non-v3 artifact path",
    ):
        evaluator._receipt_verification_lineage(
            forged_path,
            require_preserved=True,
        )


def test_v3_rejects_materialized_v2(tmp_path: Path) -> None:
    relative = evaluator.V3_V2_ABSENT_PATHS[0]
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="v2 was declared unmaterialized",
    ):
        evaluator._require_v2_absent(repository_root=tmp_path)


def test_v3_evaluator_delta_rejects_any_unapproved_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evaluator_commit = "e" * 40
    monkeypatch.setattr(
        evaluator,
        "_full_commit",
        lambda *_args, **_kwargs: evaluator_commit,
    )
    monkeypatch.setattr(
        mechanism,
        "bind_git_paths",
        lambda *_args, **_kwargs: {"source_digest": "d" * 64},
    )
    monkeypatch.setattr(
        evaluator,
        "_git_blob",
        lambda _commit, relative, **_kwargs: relative.encode("utf-8"),
    )
    allowed = "\n".join(
        evaluator.V3_ALLOWED_EVALUATOR_CHANGED_PATHS
    ).encode("utf-8")
    monkeypatch.setattr(
        mechanism,
        "_git_bytes",
        lambda *_args, **_kwargs: allowed,
    )
    checked = evaluator._validate_v3_evaluator_delta(
        evaluator_commit=evaluator_commit,
        expected_source_sha256="d" * 64,
        repository_root=tmp_path,
    )
    assert checked["changed_paths"] == list(
        evaluator.V3_ALLOWED_EVALUATOR_CHANGED_PATHS
    )

    unapproved = (
        allowed + b"\nscripts/gwip_capability_design.py\n"
    )
    monkeypatch.setattr(
        mechanism,
        "_git_bytes",
        lambda *_args, **_kwargs: unapproved,
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="escaped the preregistered source paths",
    ):
        evaluator._validate_v3_evaluator_delta(
            evaluator_commit=evaluator_commit,
            expected_source_sha256="d" * 64,
            repository_root=tmp_path,
        )


def test_v3_readiness_runs_delta_validation_before_other_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evaluator_commit = "e" * 40
    monkeypatch.setattr(
        evaluator,
        "_full_commit",
        lambda *_args, **_kwargs: evaluator_commit,
    )
    monkeypatch.setattr(
        evaluator,
        "_require_ancestry",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        evaluator,
        "_require_unchanged",
        lambda *_args, **_kwargs: None,
    )

    def reject_delta(**_kwargs) -> dict:
        raise evaluator.CapabilityEvaluationError("sentinel E3 delta")

    monkeypatch.setattr(
        evaluator,
        "_validate_v3_evaluator_delta",
        reject_delta,
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="sentinel E3 delta",
    ):
        evaluator.validate_v3_reseal_readiness(
            comparison_commit=evaluator_commit,
            repository_root=tmp_path,
        )


def test_v3_seed_runs_delta_validation_before_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evaluator_commit = "e" * 40
    output_path = tmp_path / "seed-v3.json"
    monkeypatch.setattr(
        evaluator,
        "_v1_artifact_hashes",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        evaluator,
        "_require_v2_absent",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        evaluator,
        "_v3_dataset_binding",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        evaluator,
        "_load_v1_seed_for_v3",
        lambda **_kwargs: {"generator_seed": 1, "generator_nonce": "n"},
    )
    monkeypatch.setattr(
        evaluator,
        "_full_commit",
        lambda *_args, **_kwargs: evaluator_commit,
    )
    monkeypatch.setattr(
        evaluator,
        "_head",
        lambda **_kwargs: evaluator_commit,
    )
    monkeypatch.setattr(
        evaluator,
        "_require_ancestry",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        evaluator,
        "_require_unchanged",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        mechanism,
        "_git_working_paths_unchanged",
        lambda *_args, **_kwargs: True,
    )

    def reject_delta(**_kwargs) -> dict:
        raise evaluator.CapabilityEvaluationError("sentinel E3 delta")

    monkeypatch.setattr(
        evaluator,
        "_validate_v3_evaluator_delta",
        reject_delta,
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="sentinel E3 delta",
    ):
        evaluator.create_v3_seed_manifest(
            evaluator_commit=evaluator_commit,
            output_path=output_path,
            repository_root=tmp_path,
        )
    assert not output_path.exists()


def test_v3_run_revalidates_delta_before_one_shot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = {
        "evaluator_commit": "e" * 40,
        "evaluator_source_sha256": "d" * 64,
    }
    one_shot_called = False
    monkeypatch.setattr(
        evaluator,
        "_v1_artifact_hashes",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        evaluator,
        "_require_v2_absent",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        evaluator,
        "load_sealed_seed",
        lambda **_kwargs: ({}, {"source_binding": source}),
    )

    def reject_delta(**_kwargs) -> dict:
        raise evaluator.CapabilityEvaluationError("sentinel E3 delta")

    def mark_one_shot(**_kwargs) -> dict:
        nonlocal one_shot_called
        one_shot_called = True
        return {}

    monkeypatch.setattr(
        evaluator,
        "_validate_v3_evaluator_delta",
        reject_delta,
    )
    monkeypatch.setattr(
        evaluator,
        "run_one_shot_capability",
        mark_one_shot,
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="sentinel E3 delta",
    ):
        evaluator.run_one_shot_capability_v3(
            seed_commit="s" * 40,
            external_root=tmp_path / "external",
            repository_root=tmp_path,
        )
    assert one_shot_called is False


def test_v3_existing_attempt_refuses_before_git_or_execution(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / evaluator.V3_ATTEMPT_RELATIVE_PATH
    attempt.parent.mkdir(parents=True)
    attempt.write_text("{}", encoding="utf-8")
    with evaluator._v3_run_profile():
        with pytest.raises(
            evaluator.CapabilityEvaluationError,
            match="one-shot artifacts already exist: attempt",
        ):
            evaluator.run_one_shot_capability(
                seed_commit="s" * 40,
                external_root=tmp_path / "external",
                repository_root=tmp_path,
            )


def test_v3_attempt_is_bound_before_execution() -> None:
    source = {
        "evaluator_commit": "e" * 40,
    }
    seed_binding = {
        "raw_sha256": "s" * 64,
        "source_binding": source,
    }
    with evaluator._v3_run_profile():
        evaluator._ACTIVE_VERIFICATION_LINEAGE_BASE = {
            "checksum_sha256": "l" * 64
        }
        payload = evaluator._attempt_payload(
            seed_commit="s" * 40,
            schedule_commit="l" * 40,
            seed_binding=seed_binding,
            schedule={"fixture": "schedule"},
        )
    assert payload["schema_version"] == evaluator.V3_ATTEMPT_SCHEMA
    assert payload["operator_sequence_label"] == "v3"
    assert payload["empirical_predecessor_count"] == 1
    assert payload["v2_materialized"] is False
    assert payload["retry_authorized"] is False
    assert payload["verification_lineage_sha256"] == "l" * 64


def test_v3_post_attempt_failure_seals_terminal_red(
    tmp_path: Path,
) -> None:
    source = {
        "schema_version": "atanor.gwip-capability-source-binding.v1",
        "candidate_commit": evaluator.CANDIDATE_COMMIT,
        "candidate_source_sha256": (
            evaluator.V3_CANDIDATE_SOURCE_SHA256
        ),
        "evaluator_commit": "e" * 40,
        "evaluator_source_sha256": "e" * 64,
        "seed_manifest_sha256": "s" * 64,
    }
    v1_before = evaluator._v1_artifact_hashes()
    raw_path = tmp_path / "raw-v3.json.gz"
    receipt_path = tmp_path / "receipt-v3.json"
    attempt_path = tmp_path / "attempt-v3.json"
    with evaluator._v3_run_profile():
        base = evaluator._v3_verification_lineage_base()
        base["evaluator_source_binding"] = copy.deepcopy(source)
        base["v3_evaluator_commit"] = source["evaluator_commit"]
        base["v3_evaluator_source_sha256"] = source[
            "evaluator_source_sha256"
        ]
        base["dataset_binding"][
            "v3_schedule_semantics_equal_v1"
        ] = True
        base["dataset_binding"][
            "v3_schedule_semantic_binding_sha256"
        ] = "d" * 64
        base["checksum_sha256"] = evaluator._v3_lineage_checksum(base)
        evaluator._ACTIVE_VERIFICATION_LINEAGE_BASE = base
        seed_binding = {
            "raw_sha256": "s" * 64,
            "source_binding": source,
        }
        attempt = evaluator._claim_attempt(
            seed_commit="s" * 40,
            schedule_commit="l" * 40,
            seed_binding=seed_binding,
            schedule={"fixture": "schedule"},
            output_path=attempt_path,
        )

        def fail_after_attempt() -> None:
            assert attempt_path.is_file()
            raise RuntimeError("forced immediately after A3")

        try:
            fail_after_attempt()
        except RuntimeError as failure:
            terminal = evaluator._write_terminal_after_attempt(
                failure=failure,
                seed_record={
                    "manifest": {
                        "preregistration_binding": {
                            "files": [
                                {
                                    "path": (
                                        evaluator.V3_PREREG_RELATIVE_PATH
                                    )
                                },
                                {
                                    "path": (
                                        evaluator
                                        .V3_PREREG_DOC_RELATIVE_PATH
                                    )
                                },
                            ]
                        }
                    },
                    "path": evaluator.V3_SEED_RELATIVE_PATH,
                },
                schedule_binding={
                    "path": evaluator.V3_SCHEDULE_RELATIVE_PATH
                },
                source_binding=source,
                attempt_binding=attempt,
                cohort_binding={"fixture": "cohort"},
                candidate_episodes=[],
                parent_evidence={},
                budget_probe=None,
                authority_binding=None,
                raw_path=raw_path,
                receipt_path=receipt_path,
            )
    assert attempt_path.is_file()
    assert raw_path.is_file()
    assert receipt_path.is_file()
    assert terminal["verdict"] == "CAPABILITY_RED"
    assert terminal["retry_authorized"] is False
    assert terminal["capability_claim"] is False
    assert evaluator._v1_artifact_hashes() == v1_before


def test_v3_bad_schedule_ack_leaves_attempt_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preregistration, preregistration_sha256 = (
        _install_pre_attempt_success_stubs(monkeypatch)
    )
    attempt = tmp_path / evaluator.V3_ATTEMPT_RELATIVE_PATH

    def reject_ack(**_kwargs) -> None:
        raise evaluator.CapabilityEvaluationError(
            "schedule ACK commit/blob/ancestry mismatch"
        )

    monkeypatch.setattr(
        evaluator,
        "_schedule_blob_binding",
        reject_ack,
    )
    with evaluator._v3_run_profile():
        with pytest.raises(
            evaluator.CapabilityEvaluationError,
            match="schedule ACK",
        ):
            evaluator._revalidate_before_attempt(
                seed_commit="s" * 40,
                schedule_commit="l" * 40,
                schedule={"fixture": "schedule"},
                source_binding={"fixture": "source"},
                preregistration=preregistration,
                preregistration_raw_sha256=preregistration_sha256,
                repository_root=tmp_path,
            )
    assert not attempt.exists()


def test_v3_cli_commands_are_explicit() -> None:
    parser = evaluator._build_parser()
    assert parser.parse_args(
        ["validate-reseal-v3"]
    ).command == "validate-reseal-v3"
    assert parser.parse_args(
        ["create-seed-v3", "--evaluator-commit", "e" * 40]
    ).command == "create-seed-v3"
    assert parser.parse_args(
        [
            "prepare-run-v3",
            "--seed-commit",
            "s" * 40,
            "--external-root",
            "C:/external/v3",
        ]
    ).command == "prepare-run-v3"


def test_terminal_red_receipt_is_checksum_bound(tmp_path: Path) -> None:
    raw = {
        "schema_version": evaluator.RAW_SCHEMA,
        "aggregate_metrics": None,
        "verdict": None,
    }
    raw_path = tmp_path / "raw.json.gz"
    raw_path.write_bytes(evaluator._gzip_json_bytes(raw))
    failure = RuntimeError("fixture worker failed")
    receipt = evaluator._terminal_red_receipt(
        raw_path=raw_path,
        raw_evidence=raw,
        failure=failure,
    )
    assert receipt["verdict"] == "CAPABILITY_RED"
    assert receipt["capability_claim"] is False
    assert receipt["retry_authorized"] is False
    assert receipt["checksum_sha256"] == evaluator._receipt_checksum(
        receipt
    )
    assert receipt["raw_evidence_binding"]["raw_sha256"] == hashlib.sha256(
        raw_path.read_bytes()
    ).hexdigest()
    assert "verification_lineage" not in receipt
    assert evaluator.RAW_SCHEMA == "atanor.gwip-capability-raw-evidence.v1"
    assert evaluator.RECEIPT_SCHEMA == (
        "atanor.gwip-capability-receipt.v1"
    )


def _install_pre_attempt_success_stubs(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, str]:
    preregistration = {"fixture": "frozen-p"}
    preregistration_sha256 = "a" * 64
    monkeypatch.setattr(
        evaluator,
        "_sealed_preregistration_binding",
        lambda **_kwargs: {
            "json_raw_sha256": preregistration_sha256,
            "files": [],
        },
    )
    monkeypatch.setattr(
        evaluator,
        "load_preregistration",
        lambda _path: (dict(preregistration), preregistration_sha256),
    )
    monkeypatch.setattr(
        evaluator,
        "_probe_clean_source_binding",
        lambda *_args, **_kwargs: {"source": "bound"},
    )
    monkeypatch.setattr(
        evaluator,
        "_schedule_blob_binding",
        lambda **_kwargs: {"schedule": "bound"},
    )
    return preregistration, preregistration_sha256


def test_pre_attempt_revalidation_binds_all_frozen_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preregistration, preregistration_sha256 = (
        _install_pre_attempt_success_stubs(monkeypatch)
    )
    result = evaluator._revalidate_before_attempt(
        seed_commit="s" * 40,
        schedule_commit="l" * 40,
        schedule={"fixture": "schedule"},
        source_binding={"fixture": "source"},
        preregistration=preregistration,
        preregistration_raw_sha256=preregistration_sha256,
        repository_root=tmp_path,
    )
    assert result["preregistration"] == preregistration
    assert result["preregistration"] is not preregistration
    assert result["source_binding"] == {"source": "bound"}
    assert result["schedule_binding"] == {"schedule": "bound"}


@pytest.mark.parametrize(
    ("surface", "failure"),
    (
        ("p_json", "working preregistration differs"),
        ("p_doc", "preregistration bytes changed after P"),
        ("candidate_c", "working candidate packages changed"),
        ("evaluator_e", "working evaluator bytes changed"),
        ("seed_s", "seed manifest changed"),
        ("schedule_l", "working schedule differs"),
    ),
)
def test_pre_attempt_revalidation_rejects_each_mutated_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    surface: str,
    failure: str,
) -> None:
    preregistration, preregistration_sha256 = (
        _install_pre_attempt_success_stubs(monkeypatch)
    )

    def reject(*_args: object, **_kwargs: object) -> None:
        raise evaluator.CapabilityEvaluationError(failure)

    if surface == "p_json":
        monkeypatch.setattr(
            evaluator,
            "load_preregistration",
            lambda _path: ({"fixture": "forged"}, preregistration_sha256),
        )
    elif surface == "p_doc":
        monkeypatch.setattr(
            evaluator,
            "_sealed_preregistration_binding",
            reject,
        )
    elif surface in {"candidate_c", "evaluator_e", "seed_s"}:
        monkeypatch.setattr(
            evaluator,
            "_probe_clean_source_binding",
            reject,
        )
    else:
        monkeypatch.setattr(evaluator, "_schedule_blob_binding", reject)

    with pytest.raises(evaluator.CapabilityEvaluationError, match=failure):
        evaluator._revalidate_before_attempt(
            seed_commit="s" * 40,
            schedule_commit="l" * 40,
            schedule={"fixture": "schedule"},
            source_binding={"fixture": "source"},
            preregistration=preregistration,
            preregistration_raw_sha256=preregistration_sha256,
            repository_root=tmp_path,
        )


def test_pairs_from_seed_uses_supplied_frozen_preregistration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = (object(),)
    frozen = {"fixture": "frozen-p"}
    monkeypatch.setattr(
        evaluator,
        "load_preregistration",
        lambda *_args, **_kwargs: pytest.fail(
            "working preregistration was reloaded"
        ),
    )
    monkeypatch.setattr(
        evaluator,
        "generate_capability_pairs",
        lambda value, **_kwargs: pairs if value is frozen else (),
    )
    monkeypatch.setattr(
        evaluator,
        "private_cohort_digest",
        lambda value: "cohort" if value is pairs else "wrong",
    )
    assert evaluator._pairs_from_seed(
        {"generator_seed": "seed", "generator_nonce": "nonce",
         "private_cohort_sha256": "cohort"},
        frozen,
    ) is pairs


def test_positive_receipt_is_not_published_before_identity_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    raw_path = tmp_path / "raw.json.gz"
    raw_path.write_bytes(b"raw")
    monkeypatch.setattr(
        evaluator,
        "_verify_receipt_identity",
        lambda *_args, **_kwargs: {
            "passed": False,
            "verdict": None,
            "findings": ["forged receipt"],
        },
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="before publish",
    ):
        evaluator._publish_verified_receipt(
            {"verdict": "CAPABILITY_GREEN"},
            execution_context_unwound=True,
            receipt_path=receipt_path,
            raw_path=raw_path,
            raw_evidence={},
            gate_results={},
            metrics={},
            exemplar=None,
        )
    assert not receipt_path.exists()


def test_teardown_failure_leaves_only_a_terminal_red_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    raw_path = tmp_path / "raw.json.gz"
    monkeypatch.setattr(
        evaluator,
        "_verify_receipt_identity",
        lambda *_args, **_kwargs: {
            "passed": True,
            "verdict": "CAPABILITY_GREEN",
            "findings": [],
        },
    )
    with pytest.raises(
        evaluator.CapabilityEvaluationError,
        match="contexts did not unwind",
    ):
        evaluator._publish_verified_receipt(
            {"verdict": "CAPABILITY_GREEN"},
            execution_context_unwound=False,
            receipt_path=receipt_path,
            raw_path=raw_path,
            raw_evidence={},
            gate_results={},
            metrics={},
            exemplar=None,
        )
    assert not receipt_path.exists()

    failure = RuntimeError("execution context teardown failed")
    terminal = evaluator._write_terminal_after_attempt(
        failure=failure,
        seed_record={
            "manifest": {"preregistration_binding": {"fixture": "p"}}
        },
        schedule_binding={"fixture": "l"},
        source_binding={"fixture": "source"},
        attempt_binding={"fixture": "a"},
        cohort_binding={"fixture": "cohort"},
        candidate_episodes=[],
        parent_evidence={},
        budget_probe=None,
        authority_binding=None,
        raw_path=raw_path,
        receipt_path=receipt_path,
    )
    assert terminal["verdict"] == "CAPABILITY_RED"
    assert terminal["capability_claim"] is False
    assert evaluator._read_json(
        receipt_path,
        label="teardown terminal receipt",
    ) == terminal


def test_authority_archive_preserves_episode_shards(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    shards = tmp_path / "shards"
    authority.mkdir()
    shards.mkdir()
    (authority / "public.json").write_text("authority", encoding="utf-8")
    (shards / "episode-0000.json").write_text("shard", encoding="utf-8")
    output = tmp_path / "evidence.tar.gz"
    binding = evaluator._archive_authority_root(
        authority,
        shard_root=shards,
        output_path=output,
    )
    assert binding["episode_shards_archived"] is True
    assert binding["private_signing_key_persisted"] is False
    with gzip.open(output, "rb") as compressed:
        with tarfile.open(fileobj=compressed, mode="r:") as archive:
            assert archive.getnames() == [
                "authority/public.json",
                "shards/episode-0000.json",
            ]


def test_failure_archives_exact_seed_bound_runtime_dependencies(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    (authority / "public.json").write_text("authority", encoding="utf-8")
    shards = tmp_path / "shards"
    output = tmp_path / "failure-evidence.tar.gz"
    seed_binding = census_runtime_dependency_sources(
        repository_root=evaluator.REPO
    )
    archived: dict = {}

    with pytest.raises(RuntimeError, match="forced after attempt"):
        with materialized_runtime_dependencies(
            seed_binding,
            repository_root=evaluator.REPO,
        ) as (dependency_root, _materialized_binding):
            with evaluator._archive_runtime_dependencies_on_failure(
                external_root=authority,
                shard_root=shards,
                runtime_dependency_root=dependency_root,
                expected_runtime_dependency_binding=seed_binding,
                output_path=output,
                binding_sink=archived,
            ):
                raise RuntimeError("forced after attempt")

    binding = archived["authority_binding"]
    assert binding["runtime_dependencies_archived"] is True
    assert binding["runtime_dependency_archive_verified"] is True
    assert binding["runtime_dependency_binding_sha256"] == canonical_digest(
        seed_binding
    )
    expected = {row["path"]: row for row in seed_binding["files"]}
    actual: list[dict] = []
    with tarfile.open(output, mode="r:gz") as archive:
        members = [
            member
            for member in archive.getmembers()
            if member.name.startswith("runtime-dependencies/")
        ]
        for member in members:
            logical_path = member.name[len("runtime-dependencies/") :]
            source = archive.extractfile(member)
            assert source is not None
            raw = source.read()
            actual.append(
                {
                    "dependency": expected[logical_path]["dependency"],
                    "path": logical_path,
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    assert actual == seed_binding["files"]

    forged = dict(seed_binding)
    forged["files"] = [dict(row) for row in seed_binding["files"]]
    forged["files"][0]["sha256"] = "0" * 64
    forged["tree_sha256"] = canonical_digest(forged["files"])
    forged_output = tmp_path / "forged-evidence.tar.gz"
    with materialized_runtime_dependencies(
        seed_binding,
        repository_root=evaluator.REPO,
    ) as (dependency_root, _materialized_binding):
        with pytest.raises(
            evaluator.CapabilityEvaluationError,
            match="runtime dependency root differs from seed binding",
        ):
            evaluator._archive_authority_root(
                authority,
                runtime_dependency_root=dependency_root,
                expected_runtime_dependency_binding=forged,
                output_path=forged_output,
            )
    assert not forged_output.exists()


class _IntegratedP7Environment:
    def __init__(self) -> None:
        self.value = 0
        self.live = False

    def reset(self, seed: int) -> dict:
        assert seed == 0
        self.value = 0
        self.live = True
        return {"reset": True}

    def observe(self) -> dict:
        assert self.live
        return {
            "schema_version": "fixture-p7-integrated",
            "state_ref": f"p7-state-{self.value}",
            "features": {
                "registers": [self.value],
                "context": {"modulus": 7},
            },
            "terminal": self.value == 1,
        }

    def valid_actions(self) -> list[dict]:
        assert self.live
        return [
            {
                "action_id": "p7-step",
                "payload": {"semantic_cue": "p7-opaque"},
            }
        ]

    def step(self, action_id: str) -> dict:
        assert self.live and action_id == "p7-step"
        self.value = 1
        return {
            "observation": self.observe(),
            "terminal": True,
            "success": True,
            "stop_reason": "goal_reached",
        }

    def stop(self, reason: str) -> dict:
        assert self.live and reason == "goal_reached"
        self.live = False
        return {
            "stopped": True,
            "reason": reason,
            "steps": 1,
            "success": True,
        }


def test_real_candidate_worker_crosses_parent_rpc_on_nonfinal_p7(
    tmp_path: Path,
) -> None:
    source = {
        "schema_version": "atanor.gwip-capability-source-binding.v1",
        "candidate_commit": evaluator.CANDIDATE_COMMIT,
        "candidate_source_sha256": mechanism.bind_git_candidate_tree(
            evaluator.CANDIDATE_COMMIT
        )["source_digest"],
        "evaluator_commit": "e" * 40,
        "evaluator_source_sha256": "e" * 64,
        "seed_manifest_sha256": "d" * 64,
    }
    goal = {
        "statement": "Satisfy the structured nonfinal target.",
        "origin": "explicit_user",
        "priority": 50,
        "parent_goal_ids": [],
        "constraints": [],
        "metadata": {
            "target_constraints": [
                {
                    "path": "/features/registers/0",
                    "op": "eq",
                    "value": 1,
                }
            ]
        },
    }
    environment_spec = {
        "fixture_nonproduction": True,
        "modulus": 7,
    }
    issuer = JITRunLeaseIssuer(
        tmp_path / "issuer",
        repository_root=evaluator.REPO,
    )
    episode_inputs = {
        ordinal: {
            "goal_ir": goal,
            "environment_spec": environment_spec,
        }
        for ordinal in range(64)
    }
    prepared = issuer.prepare_schedule(
        source_binding=source,
        schedule_nonce="nonfinal-p7-integrated-schedule",
        pair_count=4,
        fixture_nonproduction=True,
        episode_inputs=episode_inputs,
    )
    issuer.seal_schedule(
        prepared.schedule,
        expected_sha256=prepared.schedule_sha256,
    )
    row = prepared.schedule["rows"][0]
    memory = canonical_empty_memory()
    request = {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "ordinal": row["ordinal"],
        "schedule_row_sha256": canonical_digest(row),
        "phase": row["phase"],
        "pair_index": row["pair_index"],
        "episode_index": row["episode_index"],
        "arm": row["arm"],
        "environment_seed": row["environment_seed"],
        "policy_seed": row["policy_seed"],
        "step_budget": row["step_budget"],
        "retain_policy_updates": row["retain_policy_updates"],
        "session_id": "nonfinal-p7-integrated",
        "goal_ir": goal,
        "environment_spec": environment_spec,
        "policy_memory": memory,
        "policy_memory_sha256": canonical_digest(memory),
        "episode_input_sha256": row["episode_input_sha256"],
        "source_binding_sha256": prepared.schedule[
            "source_binding_sha256"
        ],
    }
    authority = issuer.issue(prepared.schedule, ordinal=0)
    authority.activate()
    sink = ThreadSafeEvidenceSink()
    dependency_binding = census_runtime_dependency_sources(
        repository_root=evaluator.REPO
    )
    with (
        evaluator.sealed_capability_candidate_source(
            evaluator.CANDIDATE_COMMIT
        ) as (candidate_root, _binding),
        materialized_runtime_dependencies(
            dependency_binding,
            repository_root=evaluator.REPO,
        ) as (dependency_root, materialized_binding),
    ):
        runner = CandidateEpisodeRunner(
            candidate_root=candidate_root,
            worker_script=(
                evaluator.REPO / "scripts" / "gwip_capability_worker.py"
            ),
            evidence_sink=sink,
            environment_factory=lambda _request, _session: (
                _IntegratedP7Environment()
            ),
            source_probe=lambda: source,
            repository_root=evaluator.REPO,
            runtime_dependency_root=dependency_root,
            runtime_dependency_binding=materialized_binding,
            timeout_seconds=30,
        )
        result = runner(request, authority)
    assert result["trace"]["semantic_trace"]["success"] is True
    assert result["worker_claims"]["capability_verdict"] is None
    assert sink.get(0)["status"] == "complete"
    assert authority.seal(shard_sha256="a" * 64)["passed"] is True
