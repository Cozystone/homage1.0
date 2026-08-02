"""No-regression accepts only externally signed, scope-bound evaluation receipts."""
from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from packages.autonomy_envelope import AutonomyEnvelope
from packages.autonomy_envelope.evaluation_trust import (
    verify_evaluation_receipt,
)
from packages.autonomy_envelope.tests.evaluation_helpers import (
    evaluation_keypair,
    sign_document,
    signed_evaluation,
)


def _configured(tmp_path):
    private, trust_root = evaluation_keypair()
    env = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)
    return env, private, trust_root


def _receipt(env, private, trust_root, score, suffix, **kwargs):
    return signed_evaluation(
        oracle_fingerprint=env.oracle.fingerprint,
        private=private,
        trust_root=trust_root,
        score=score,
        run_id=f"evaluation-run-{suffix}",
        nonce=f"evaluation-nonce-{suffix:0>4}",
        **kwargs,
    )


def test_default_has_no_evaluation_authority_and_raw_score_never_ratchets(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    decision = env.mark_cycle(0.99, evidence={"claimed": "perfect"})
    assert decision.allowed is False
    assert env.evaluation_ratchet.status()["scope_count"] == 0
    status = env.status()
    assert status["external_evaluator_configured"] is False
    assert status["evaluation_authority_ready"] is False
    assert status["oracle_spec_integrity_ok"] is True
    assert status["baseline"] is None


def test_configured_authority_still_rejects_raw_score_and_evidence(tmp_path):
    env, _, _ = _configured(tmp_path)
    assert env.mark_cycle(0.8).allowed is False
    assert env.mark_cycle({"score": 0.8}, evidence={}).allowed is False
    assert env.evaluation_ratchet.status()["scope_count"] == 0


def test_valid_signed_receipt_ratchets_and_replay_is_rejected(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    first = env.mark_cycle(receipt, live_context=context)
    assert first.allowed is True
    assert first.meta["baseline_before"] is None
    assert first.meta["baseline_after"] == 0.8

    replay = env.mark_cycle(receipt, live_context=context)
    assert replay.allowed is False
    assert replay.reason == "evaluation_receipt_replay"
    assert env.evaluation_ratchet.baseline == 0.8


def test_baseline_persists_and_is_authenticated_on_reconstruction(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.82, "0001")
    assert env.mark_cycle(receipt, live_context=context).allowed is True

    reopened = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)
    assert reopened.evaluation_ratchet.baseline == 0.82
    assert reopened.status()["evaluation_state_ok"] is True

    state_path = tmp_path / "evaluation_ratchet_v1.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    only_scope = next(iter(state["scopes"].values()))
    only_scope["baseline"] = 0.1
    state_path.write_text(json.dumps(state), encoding="utf-8")

    tampered = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)
    status = tampered.status()
    assert status["evaluation_state_ok"] is False
    assert status["evaluation_authority_ready"] is False

    next_receipt, next_context = _receipt(
        tampered, private, trust_root, 0.9, "0002"
    )
    denied = tampered.mark_cycle(next_receipt, live_context=next_context)
    assert denied.allowed is False
    assert "state" in denied.reason


def test_regression_is_blocked_and_consumed_but_improvement_ratchets(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    first, first_context = _receipt(env, private, trust_root, 0.8, "0001")
    assert env.mark_cycle(first, live_context=first_context).allowed is True

    lower, lower_context = _receipt(env, private, trust_root, 0.7, "0002")
    denied = env.mark_cycle(lower, live_context=lower_context)
    assert denied.allowed is False
    assert denied.reason == "evaluation_regression_blocked"
    assert env.evaluation_ratchet.baseline == 0.8
    assert env.mark_cycle(lower, live_context=lower_context).reason == (
        "evaluation_receipt_replay"
    )

    higher, higher_context = _receipt(env, private, trust_root, 0.9, "0003")
    assert env.mark_cycle(higher, live_context=higher_context).allowed is True
    assert env.evaluation_ratchet.baseline == 0.9


def test_incomparable_scopes_have_independent_baselines(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    scope_a, context_a = _receipt(env, private, trust_root, 0.9, "0001")
    assert env.mark_cycle(scope_a, live_context=context_a).allowed is True

    scope_b, context_b = _receipt(
        env,
        private,
        trust_root,
        0.2,
        "0002",
        suite_digest_sha256="a" * 64,
    )
    second = env.mark_cycle(scope_b, live_context=context_b)
    assert second.allowed is True
    status = env.evaluation_ratchet.status()
    assert status["scope_count"] == 2
    assert sorted(status["baselines"].values()) == [0.2, 0.9]
    assert env.evaluation_ratchet.baseline is None


@pytest.mark.parametrize("bad_score", [True, "0.9", -0.01, 1.01, math.nan, math.inf])
def test_nonliteral_nonfinite_or_out_of_range_scores_fail_closed(
    tmp_path, bad_score
):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.5, "0001")
    receipt["score"] = bad_score
    context["score"] = bad_score
    result = env.mark_cycle(receipt, live_context=context)
    assert result.allowed is False
    assert "score_invalid" in result.reason
    assert env.evaluation_ratchet.status()["scope_count"] == 0


def test_exact_schema_signature_and_live_context_are_mandatory(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")

    unsigned = dict(receipt)
    unsigned.pop("operator_signature")
    assert env.mark_cycle(unsigned, live_context=context).allowed is False

    with_extra = dict(receipt)
    with_extra["unreviewed_authority"] = True
    sign_document(with_extra, private, trust_root)
    assert env.mark_cycle(with_extra, live_context=context).allowed is False

    assert env.mark_cycle(receipt).allowed is False
    extra_context = dict(context)
    extra_context["unreviewed"] = True
    assert env.mark_cycle(receipt, live_context=extra_context).allowed is False

    changed = dict(context)
    changed["outcome_digest_sha256"] = "f" * 64
    assert env.mark_cycle(receipt, live_context=changed).allowed is False


@pytest.mark.parametrize(
    "field",
    [
        "oracle_fingerprint",
        "metric_digest_sha256",
        "suite_digest_sha256",
        "dataset_digest_sha256",
        "candidate_digest_sha256",
        "evaluator_digest_sha256",
        "outcome_digest_sha256",
        "score",
        "run_id",
    ],
)
def test_every_live_evaluation_binding_must_match(tmp_path, field):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    if field == "score":
        context[field] = 0.7
    elif field == "run_id":
        context[field] = "different-run"
    else:
        context[field] = "f" * 64
    result = env.mark_cycle(receipt, live_context=context)
    assert result.allowed is False
    assert field in result.reason


def test_receipt_is_time_bounded_and_purpose_bound(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expired, expired_context = _receipt(
        env,
        private,
        trust_root,
        0.8,
        "0001",
        issued_at=(now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    assert "expired" in env.mark_cycle(expired, live_context=expired_context).reason

    wrong, wrong_context = _receipt(
        env,
        private,
        trust_root,
        0.8,
        "0002",
        purpose="atanor.shipped-graph-promotion.v1",
    )
    assert env.mark_cycle(wrong, live_context=wrong_context).allowed is False


def test_full_moral_and_oracle_integrity_precede_receipt_acceptance(
    tmp_path, monkeypatch
):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    monkeypatch.setattr(
        env.moral,
        "verify_integrity",
        lambda: {"ok": False, "reason": "moral tampered"},
    )
    denied = env.mark_cycle(receipt, live_context=context)
    assert denied.allowed is False
    assert env.evaluation_ratchet.status()["consumed_nonce_count"] == 0


def test_standalone_verifier_requires_live_oracle_and_operator_key(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    _, other_root = evaluation_keypair()
    wrong_key = verify_evaluation_receipt(
        receipt,
        trust_root=other_root,
        live_context=context,
        live_oracle_fingerprint=env.oracle.fingerprint,
    )
    assert wrong_key.ok is False

    wrong_oracle = verify_evaluation_receipt(
        receipt,
        trust_root=trust_root,
        live_context=context,
        live_oracle_fingerprint="f" * 64,
    )
    assert wrong_oracle.ok is False


@pytest.mark.parametrize(
    "forged_fields",
    [
        {"scope_id": "f" * 64},
        {"score": 0.99},
        {"nonce": "forged-evaluation-nonce-0001"},
        {"run_id": "forged-evaluation-run"},
        {"key_id": "forged-evaluator-key"},
        {
            "scope_bindings": (
                ("oracle_fingerprint", "f" * 64),
                ("metric_digest_sha256", "f" * 64),
                ("suite_digest_sha256", "f" * 64),
                ("dataset_digest_sha256", "f" * 64),
                ("evaluator_digest_sha256", "f" * 64),
            )
        },
        {"reason": "forged_validity_claim"},
    ],
)
def test_direct_ratchet_apply_cannot_use_forged_verification_fields(
    tmp_path,
    forged_fields,
):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    verified = verify_evaluation_receipt(
        receipt,
        trust_root=trust_root,
        live_context=context,
        live_oracle_fingerprint=env.oracle.fingerprint,
    )
    assert verified.ok is True

    forged = replace(verified, **forged_fields)
    denied = env.evaluation_ratchet._apply_verified(forged, receipt=receipt)

    assert denied.allowed is False
    assert denied.reason == "verified_evaluation_binding_mismatch"
    assert env.evaluation_ratchet.status()["scope_count"] == 0
    assert env.evaluation_ratchet.status()["consumed_nonce_count"] == 0


def test_public_ratchet_apply_rejects_malformed_input_without_crashing(
    tmp_path,
):
    env, _, _ = _configured(tmp_path)

    denied = env.evaluation_ratchet.apply(
        receipt=object(),
        live_context={},
    )

    assert denied.allowed is False
    assert denied.reason == "evaluation_receipt_or_live_context_unreadable"
    assert denied.scope_id is None
    assert denied.score is None
    assert env.evaluation_ratchet.status()["scope_count"] == 0


@pytest.mark.parametrize("forged_score", [True, 1])
def test_direct_ratchet_apply_rejects_bool_or_int_verification_score_alias(
    tmp_path,
    forged_score,
):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 1.0, "0001")
    verified = verify_evaluation_receipt(
        receipt,
        trust_root=trust_root,
        live_context=context,
        live_oracle_fingerprint=env.oracle.fingerprint,
    )
    assert verified.score == 1.0
    assert type(verified.score) is float

    denied = env.evaluation_ratchet._apply_verified(
        replace(verified, score=forged_score),
        receipt=receipt,
    )

    assert denied.allowed is False
    assert denied.reason == "verified_evaluation_receipt_required"
    assert env.evaluation_ratchet.status()["scope_count"] == 0
    assert env.evaluation_ratchet.status()["consumed_nonce_count"] == 0


def test_public_ratchet_apply_reverifies_live_context_itself(tmp_path):
    env, private, trust_root = _configured(tmp_path)
    receipt, context = _receipt(env, private, trust_root, 0.8, "0001")
    forged_context = dict(context)
    forged_context["candidate_digest_sha256"] = "f" * 64

    denied = env.evaluation_ratchet.apply(
        receipt=receipt,
        live_context=forged_context,
    )

    assert denied.allowed is False
    assert denied.reason == "evaluation_live_candidate_digest_sha256_mismatch"
    assert env.evaluation_ratchet.status()["scope_count"] == 0
    assert env.evaluation_ratchet.status()["consumed_nonce_count"] == 0

    accepted = env.evaluation_ratchet.apply(
        receipt=receipt,
        live_context=context,
    )
    assert accepted.allowed is True
    assert accepted.baseline_after == 0.8
