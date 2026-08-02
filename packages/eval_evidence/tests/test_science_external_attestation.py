"""Science-specific binding of external assertions to the generic trust layer."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from packages.autonomy_envelope.evaluation_trust import EvaluationRatchetStore
from packages.autonomy_envelope.tests.evaluation_helpers import (
    evaluation_keypair,
    signed_evaluation,
)
from packages.eval_evidence.receipt import canonical_json_bytes
from packages.eval_evidence.science_external_attestation import (
    SCIENCE_PRECOMMIT_SCHEMA_VERSION,
    SCIENCE_RESULT_ROOT_SCHEMA_VERSION,
    ScienceExternalAttestationError,
    consume_science_external_attestation,
    derive_science_evaluation_live_context,
    read_science_precommit,
    read_science_result_root,
)


def _digest(value: Any) -> str:
    payload = (
        value
        if isinstance(value, bytes)
        else canonical_json_bytes(value)
    )
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _precommit(evaluator_key_id: str, operator_key_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_PRECOMMIT_SCHEMA_VERSION,
        "protocol_id": "science-independent-e4-binding-fixture-v1",
        "oracle_spec_digest_sha256": "1" * 64,
        "metric_spec_digest_sha256": "2" * 64,
        "dataset_manifest_digest_sha256": "3" * 64,
        "candidate_manifest_digest_sha256": "4" * 64,
        "stage_manifest_digest_sha256": "5" * 64,
        "evaluator_manifest_digest_sha256": "6" * 64,
        "evaluation_config_digest_sha256": "7" * 64,
        "order_digest_sha256": "8" * 64,
        "isolation_contract_digest_sha256": "9" * 64,
        "evaluator_key_id": evaluator_key_id,
        "promotion_operator_key_id": operator_key_id,
    }


def _result_root(
    precommit: dict[str, Any],
    *,
    score: float = 0.625,
    run_id: str = "science-external-run-0001",
) -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_RESULT_ROOT_SCHEMA_VERSION,
        "precommit_digest_sha256": _digest(precommit),
        "run_id": run_id,
        "score": score,
        "executed_order_digest_sha256": precommit[
            "order_digest_sha256"
        ],
        "result_artifact_digest_sha256": "a" * 64,
        "claims": {
            "os_isolation_established": False,
            "independent_evaluation_established": False,
            "canonical_e4_established": False,
            "e5_established": False,
        },
    }


def _signed_receipt(
    *,
    private,
    trust_root,
    context: dict[str, Any],
    nonce: str = "science-evaluator-nonce-0001",
) -> tuple[dict[str, Any], bytes]:
    receipt, helper_context = signed_evaluation(
        oracle_fingerprint=context["oracle_fingerprint"],
        private=private,
        trust_root=trust_root,
        score=context["score"],
        run_id=context["run_id"],
        nonce=nonce,
        metric_digest_sha256=context["metric_digest_sha256"],
        suite_digest_sha256=context["suite_digest_sha256"],
        dataset_digest_sha256=context["dataset_digest_sha256"],
        candidate_digest_sha256=context["candidate_digest_sha256"],
        evaluator_digest_sha256=context["evaluator_digest_sha256"],
        outcome_digest_sha256=context["outcome_digest_sha256"],
    )
    assert helper_context == context
    return receipt, _canonical(receipt)


def _fixture(tmp_path: Path) -> dict[str, Any]:
    evaluator_private, evaluator_root = evaluation_keypair()
    _, operator_root = evaluation_keypair()
    assert evaluator_root.key_id != operator_root.key_id
    precommit = _precommit(evaluator_root.key_id, operator_root.key_id)
    result_root = _result_root(precommit)
    context = derive_science_evaluation_live_context(
        precommit,
        result_root,
    )
    receipt, receipt_bytes = _signed_receipt(
        private=evaluator_private,
        trust_root=evaluator_root,
        context=context,
    )
    store = EvaluationRatchetStore(
        tmp_path / "science-ratchet",
        oracle_fingerprint=context["oracle_fingerprint"],
        trust_root=evaluator_root,
    )
    return {
        "evaluator_private": evaluator_private,
        "evaluator_root": evaluator_root,
        "operator_root": operator_root,
        "precommit": precommit,
        "result_root": result_root,
        "context": context,
        "receipt": receipt,
        "receipt_bytes": receipt_bytes,
        "store": store,
    }


def _consume(fixture: dict[str, Any], **overrides: Any):
    arguments = {
        "signed_receipt_bytes": fixture["receipt_bytes"],
        "precommit_bytes": _canonical(fixture["precommit"]),
        "result_root_bytes": _canonical(fixture["result_root"]),
        "evaluator_trust_root": fixture["evaluator_root"],
        "ratchet_store": fixture["store"],
        "promotion_operator_key_id": fixture["operator_root"].key_id,
    }
    arguments.update(overrides)
    return consume_science_external_attestation(**arguments)


def test_mapping_is_deterministic_and_binds_full_roots(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    precommit = fixture["precommit"]
    result_root = fixture["result_root"]

    first = derive_science_evaluation_live_context(precommit, result_root)
    second = derive_science_evaluation_live_context(
        json.loads(json.dumps(precommit)),
        json.loads(json.dumps(result_root)),
    )

    assert first == second
    assert first == fixture["context"]
    assert first["oracle_fingerprint"] == precommit[
        "oracle_spec_digest_sha256"
    ]
    assert first["metric_digest_sha256"] == precommit[
        "metric_spec_digest_sha256"
    ]
    assert first["suite_digest_sha256"] == _digest(
        {
            "schema_version": precommit["schema_version"],
            "protocol_id": precommit["protocol_id"],
            "evaluation_config_digest_sha256": precommit[
                "evaluation_config_digest_sha256"
            ],
            "order_digest_sha256": precommit["order_digest_sha256"],
            "isolation_contract_digest_sha256": precommit[
                "isolation_contract_digest_sha256"
            ],
            "evaluator_key_id": precommit["evaluator_key_id"],
            "promotion_operator_key_id": precommit[
                "promotion_operator_key_id"
            ],
        }
    )
    assert first["dataset_digest_sha256"] == precommit[
        "dataset_manifest_digest_sha256"
    ]
    assert first["candidate_digest_sha256"] == _digest(
        {
            "candidate_manifest_digest_sha256": precommit[
                "candidate_manifest_digest_sha256"
            ],
            "stage_manifest_digest_sha256": precommit[
                "stage_manifest_digest_sha256"
            ],
        }
    )
    assert first["evaluator_digest_sha256"] == precommit[
        "evaluator_manifest_digest_sha256"
    ]
    assert first["outcome_digest_sha256"] == _digest(result_root)
    assert first["score"] == result_root["score"]
    assert first["run_id"] == result_root["run_id"]


def test_valid_assertion_claims_nonce_once_and_replay_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    first = _consume(fixture)
    replay = _consume(fixture)

    assert first.local_ratchet_allowed is True
    assert first.reason == "evaluation_holds_line"
    assert first.signed_live_binding_valid is True
    assert first.nonce_claimed_by_this_call is True
    assert first.score == 0.625
    assert first.baseline_before is None
    assert first.baseline_after == 0.625
    assert replay.local_ratchet_allowed is False
    assert replay.reason == "evaluation_receipt_replay"
    assert replay.signed_live_binding_valid is True
    assert replay.nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 1


def test_concurrent_replay_never_claims_the_winning_nonce(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: _consume(fixture), range(2)))

    winner = [row for row in results if row.local_ratchet_allowed]
    replay = [row for row in results if row.reason == "evaluation_receipt_replay"]
    assert len(winner) == 1
    assert len(replay) == 1
    assert winner[0].nonce_claimed_by_this_call is True
    assert replay[0].nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 1


def test_valid_signature_does_not_claim_isolation_independence_e4_or_e5(
    tmp_path: Path,
) -> None:
    result = _consume(_fixture(tmp_path))

    assert result.local_ratchet_allowed is True
    assert result.os_isolation_established is False
    assert result.independent_evaluation_established is False
    assert result.canonical_e4_established is False
    assert result.e5_established is False
    assert result.to_dict()[
        "independent_evaluation_established"
    ] is False


def test_candidate_revision_stays_in_scope_and_lower_score_is_blocked(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first_result = dict(fixture["result_root"])
    first_result["score"] = 0.75
    first_context = derive_science_evaluation_live_context(
        fixture["precommit"],
        first_result,
    )
    _, first_receipt_bytes = _signed_receipt(
        private=fixture["evaluator_private"],
        trust_root=fixture["evaluator_root"],
        context=first_context,
        nonce="science-evaluator-nonce-candidate-a",
    )
    first = _consume(
        fixture,
        signed_receipt_bytes=first_receipt_bytes,
        result_root_bytes=_canonical(first_result),
    )

    second_precommit = dict(fixture["precommit"])
    second_precommit["candidate_manifest_digest_sha256"] = "b" * 64
    second_precommit["stage_manifest_digest_sha256"] = "c" * 64
    second_result = _result_root(
        second_precommit,
        score=0.5,
        run_id="science-external-run-0002",
    )
    second_context = derive_science_evaluation_live_context(
        second_precommit,
        second_result,
    )
    _, second_receipt_bytes = _signed_receipt(
        private=fixture["evaluator_private"],
        trust_root=fixture["evaluator_root"],
        context=second_context,
        nonce="science-evaluator-nonce-candidate-b",
    )
    second = _consume(
        fixture,
        signed_receipt_bytes=second_receipt_bytes,
        precommit_bytes=_canonical(second_precommit),
        result_root_bytes=_canonical(second_result),
    )

    assert first.local_ratchet_allowed is True
    assert second_context["suite_digest_sha256"] == (
        first_context["suite_digest_sha256"]
    )
    assert second_context["candidate_digest_sha256"] != (
        first_context["candidate_digest_sha256"]
    )
    assert second.local_ratchet_allowed is False
    assert second.reason == "evaluation_regression_blocked"
    assert second.scope_id == first.scope_id
    assert second.baseline_before == 0.75
    assert second.baseline_after == 0.75
    assert second.nonce_claimed_by_this_call is True


@pytest.mark.parametrize(
    "document",
    ["precommit", "result_root"],
)
def test_exact_schemas_reject_extra_fields(
    tmp_path: Path,
    document: str,
) -> None:
    fixture = _fixture(tmp_path)
    changed = dict(fixture[document])
    changed["extra_authority"] = True
    overrides = {
        f"{document}_bytes": _canonical(changed),
    }

    denied = _consume(fixture, **overrides)

    assert denied.local_ratchet_allowed is False
    assert denied.signed_live_binding_valid is False
    assert denied.nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 0


@pytest.mark.parametrize(
    "payload_kind,payload",
    [
        ("precommit_bytes", b'{"schema_version":1,"schema_version":1}\n'),
        ("precommit_bytes", b"{}\n\n"),
        ("result_root_bytes", b"{}"),
        ("signed_receipt_bytes", b"not-json\n"),
    ],
)
def test_noncanonical_duplicate_or_malformed_bytes_fail_before_nonce(
    tmp_path: Path,
    payload_kind: str,
    payload: bytes,
) -> None:
    fixture = _fixture(tmp_path)

    denied = _consume(fixture, **{payload_kind: payload})

    assert denied.local_ratchet_allowed is False
    assert denied.signed_live_binding_valid is False
    assert denied.nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_parser_requires_one_canonical_trailing_newline(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    precommit = fixture["precommit"]

    assert read_science_precommit(_canonical(precommit)) == precommit
    with pytest.raises(
        ScienceExternalAttestationError,
        match="one trailing newline",
    ):
        read_science_precommit(canonical_json_bytes(precommit))


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("oracle_spec_digest_sha256", "b" * 64),
        ("metric_spec_digest_sha256", "b" * 64),
        ("dataset_manifest_digest_sha256", "b" * 64),
        ("candidate_manifest_digest_sha256", "b" * 64),
        ("stage_manifest_digest_sha256", "b" * 64),
        ("evaluator_manifest_digest_sha256", "b" * 64),
        ("evaluation_config_digest_sha256", "b" * 64),
        ("order_digest_sha256", "b" * 64),
        ("isolation_contract_digest_sha256", "b" * 64),
    ],
)
def test_every_precommit_binding_drift_fails_before_nonce(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path)
    precommit = dict(fixture["precommit"])
    precommit[field] = replacement
    result_root = dict(fixture["result_root"])
    result_root["precommit_digest_sha256"] = _digest(precommit)
    if field == "order_digest_sha256":
        result_root["executed_order_digest_sha256"] = replacement

    denied = _consume(
        fixture,
        precommit_bytes=_canonical(precommit),
        result_root_bytes=_canonical(result_root),
    )

    assert denied.local_ratchet_allowed is False
    assert denied.signed_live_binding_valid is False
    assert denied.nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_result_artifact_drift_fails_signed_live_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    result_root = dict(fixture["result_root"])
    result_root["result_artifact_digest_sha256"] = "b" * 64

    denied = _consume(
        fixture,
        result_root_bytes=_canonical(result_root),
    )

    assert denied.local_ratchet_allowed is False
    assert denied.reason == "evaluation_live_outcome_digest_sha256_mismatch"
    assert denied.signed_live_binding_valid is False
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_result_execution_order_must_equal_precommit(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    result_root = dict(fixture["result_root"])
    result_root["executed_order_digest_sha256"] = "b" * 64

    denied = _consume(
        fixture,
        result_root_bytes=_canonical(result_root),
    )

    assert denied.local_ratchet_allowed is False
    assert "execution order mismatch" in denied.reason
    assert fixture["store"].status()["consumed_nonce_count"] == 0


@pytest.mark.parametrize(
    "claim",
    [
        "os_isolation_established",
        "independent_evaluation_established",
        "canonical_e4_established",
        "e5_established",
    ],
)
def test_result_root_cannot_self_assert_external_authority(
    tmp_path: Path,
    claim: str,
) -> None:
    fixture = _fixture(tmp_path)
    result_root = json.loads(json.dumps(fixture["result_root"]))
    result_root["claims"][claim] = True

    denied = _consume(
        fixture,
        result_root_bytes=_canonical(result_root),
    )

    assert denied.local_ratchet_allowed is False
    assert f"{claim} must remain false" in denied.reason
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_evaluator_and_promotion_operator_keys_must_be_distinct(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    precommit = _precommit(
        fixture["evaluator_root"].key_id,
        fixture["evaluator_root"].key_id,
    )
    result_root = _result_root(precommit)

    denied = _consume(
        fixture,
        precommit_bytes=_canonical(precommit),
        result_root_bytes=_canonical(result_root),
        promotion_operator_key_id=fixture["evaluator_root"].key_id,
    )

    assert denied.local_ratchet_allowed is False
    assert "must be distinct" in denied.reason
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_wrong_external_operator_pin_fails_before_nonce(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _, other_operator = evaluation_keypair()

    denied = _consume(
        fixture,
        promotion_operator_key_id=other_operator.key_id,
    )

    assert denied.local_ratchet_allowed is False
    assert denied.reason == "science_promotion_operator_key_id_mismatch"
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_wrong_evaluator_key_or_store_key_fails_before_nonce(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _, wrong_evaluator = evaluation_keypair()
    wrong_key = _consume(
        fixture,
        evaluator_trust_root=wrong_evaluator,
    )

    wrong_store = EvaluationRatchetStore(
        tmp_path / "wrong-key-store",
        oracle_fingerprint=fixture["context"]["oracle_fingerprint"],
        trust_root=wrong_evaluator,
    )
    wrong_ratchet = _consume(fixture, ratchet_store=wrong_store)

    assert wrong_key.reason == "science_evaluator_key_id_mismatch"
    assert wrong_ratchet.reason == "science_evaluation_ratchet_key_mismatch"
    assert fixture["store"].status()["consumed_nonce_count"] == 0
    assert wrong_store.status()["consumed_nonce_count"] == 0


def test_tampered_signed_receipt_fails_before_nonce(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt = json.loads(json.dumps(fixture["receipt"]))
    receipt["score"] = 0.75

    denied = _consume(
        fixture,
        signed_receipt_bytes=_canonical(receipt),
    )

    assert denied.local_ratchet_allowed is False
    assert denied.signed_live_binding_valid is False
    assert denied.nonce_claimed_by_this_call is False
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_bool_score_and_precommit_result_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    bool_score = dict(fixture["result_root"])
    bool_score["score"] = True
    mismatched = dict(fixture["result_root"])
    mismatched["precommit_digest_sha256"] = "b" * 64

    first = _consume(
        fixture,
        result_root_bytes=_canonical(bool_score),
    )
    second = _consume(
        fixture,
        result_root_bytes=_canonical(mismatched),
    )

    assert first.local_ratchet_allowed is False
    assert "score invalid" in first.reason
    assert second.local_ratchet_allowed is False
    assert "precommit digest mismatch" in second.reason
    assert fixture["store"].status()["consumed_nonce_count"] == 0


def test_public_result_parser_revalidates_precommit_and_claim_limits(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    assert read_science_result_root(
        _canonical(fixture["result_root"]),
        precommit=fixture["precommit"],
    ) == fixture["result_root"]

    malformed = dict(fixture["precommit"])
    malformed["promotion_operator_key_id"] = malformed["evaluator_key_id"]
    with pytest.raises(ScienceExternalAttestationError, match="distinct"):
        read_science_result_root(
            _canonical(fixture["result_root"]),
            precommit=malformed,
        )
