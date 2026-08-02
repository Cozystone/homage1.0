"""Operator trust is externally signed, purpose-bound, and fail-closed."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    MORAL_POLICY_PURPOSE,
    SHIPPED_GRAPH_PURPOSE,
    SHIPPED_GRAPH_SCHEMA_VERSION,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    canonical_payload_bytes,
    payload_sha256,
    verify_moral_policy,
    verify_shipped_graph_promotion,
    verify_shipped_graph_promotion_historical,
)


def _keypair() -> tuple[Ed25519PrivateKey, OperatorTrustRoot, bytes]:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"
    return private, OperatorTrustRoot(pem, expected_key_id=key_id), pem


def _sign(document, private, root):
    digest = payload_sha256(document)
    signature = private.sign(canonical_payload_bytes(document))
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": root.key_id,
        "payload_sha256": digest,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return document


def _promotion_payload(**overrides):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "schema_version": SHIPPED_GRAPH_SCHEMA_VERSION,
        "purpose": SHIPPED_GRAPH_PURPOSE,
        "merge_authorized": True,
        "production_store_mutated": False,
        "rollback_required": True,
        "staging_receipt_sha256": "1" * 64,
        "candidate_digest_sha256": "2" * 64,
        "mutation_batch_manifest_sha256": "7" * 64,
        "item_ids": ["edge-1"],
        "target_store_id": "shipped-graph-primary",
        "operator_boundary_id": "atanor:test:shipped-graph-boundary",
        "operator_boundary_config_sha256": "4" * 64,
        "base_revision": "revision-42",
        "rollback_artifact_sha256": "3" * 64,
        "nonce_replay_domain": {
            "schema_version": "atanor.promotion-nonce-replay-domain.v1",
            "ledger_id": "atanor:promotion-ledger:test-domain-00000001",
            "target_store_id": "shipped-graph-primary",
            "resolved_root_sha256": "5" * 64,
            "identity_manifest_sha256": "6" * 64,
            "lock_relative_path": ".shipped-store-promotion.lock",
            "claims_relative_path": "claims",
        },
        "issued_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": "promotion-nonce-0001",
    }
    payload.update(overrides)
    return payload


def _live_context(payload):
    return {
        field: payload[field]
        for field in (
            "staging_receipt_sha256",
            "candidate_digest_sha256",
            "mutation_batch_manifest_sha256",
            "item_ids",
            "target_store_id",
            "operator_boundary_id",
            "operator_boundary_config_sha256",
            "base_revision",
            "rollback_artifact_sha256",
            "nonce_replay_domain",
        )
    }


def test_valid_external_signature_binds_live_moral_fingerprint():
    private, root, _ = _keypair()
    document = _sign(
        {
            "schema_version": "atanor.operator-policy.v1",
            "purpose": MORAL_POLICY_PURPOSE,
            "moral_fingerprint": "a" * 64,
            "policy_version": 1,
        },
        private,
        root,
    )
    result = verify_moral_policy(
        document,
        live_moral_fingerprint="a" * 64,
        trust_root=root,
    )
    assert result.ok is True
    assert result.reason == "operator_signature_valid"


def test_payload_tamper_after_signature_fails_closed():
    private, root, _ = _keypair()
    document = _sign(
        {
            "purpose": MORAL_POLICY_PURPOSE,
            "moral_fingerprint": "a" * 64,
        },
        private,
        root,
    )
    document["moral_fingerprint"] = "b" * 64
    result = verify_moral_policy(
        document,
        live_moral_fingerprint="b" * 64,
        trust_root=root,
    )
    assert result.ok is False
    assert result.reason == "payload_digest_mismatch"


def test_validly_signed_different_moral_core_does_not_authorize_live_core():
    private, root, _ = _keypair()
    document = _sign(
        {
            "purpose": MORAL_POLICY_PURPOSE,
            "moral_fingerprint": "b" * 64,
        },
        private,
        root,
    )
    result = verify_moral_policy(
        document,
        live_moral_fingerprint="a" * 64,
        trust_root=root,
    )
    assert result.ok is False
    assert result.reason == "live_moral_fingerprint_mismatch"


def test_missing_malformed_or_wrong_key_signature_fails_closed():
    private, root, _ = _keypair()
    unsigned = {"purpose": MORAL_POLICY_PURPOSE, "moral_fingerprint": "a" * 64}
    assert root.verify_document(
        unsigned,
        required_purpose=MORAL_POLICY_PURPOSE,
    ).reason == "operator_signature_missing"

    malformed = dict(unsigned)
    malformed[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": root.key_id,
        "payload_sha256": payload_sha256(malformed),
        "signature": "not base64!!!",
    }
    assert root.verify_document(
        malformed,
        required_purpose=MORAL_POLICY_PURPOSE,
    ).reason == "signature_encoding_invalid"

    other_private, other_root, _ = _keypair()
    wrong_key = _sign(dict(unsigned), other_private, other_root)
    assert root.verify_document(
        wrong_key,
        required_purpose=MORAL_POLICY_PURPOSE,
    ).reason == "operator_key_mismatch"


def test_purpose_is_not_reusable_across_moral_and_graph_authority():
    private, root, _ = _keypair()
    moral = _sign(
        {
            "purpose": MORAL_POLICY_PURPOSE,
            "moral_fingerprint": "a" * 64,
            "production_store_mutated": False,
            "rollback_required": True,
        },
        private,
        root,
    )
    result = verify_shipped_graph_promotion(moral, trust_root=root)
    assert result.ok is False
    assert result.reason == "purpose_mismatch"


def test_shipped_graph_signature_requires_premerge_and_rollback_contract():
    private, root, _ = _keypair()
    payload = _promotion_payload()
    valid = _sign(payload, private, root)
    assert verify_shipped_graph_promotion(
        valid,
        trust_root=root,
        live_context=_live_context(valid),
    ).ok is True

    mutated_payload = _promotion_payload(production_store_mutated=True)
    mutated = _sign(mutated_payload, private, root)
    assert verify_shipped_graph_promotion(
        mutated,
        trust_root=root,
        live_context=_live_context(mutated),
    ).reason == "preverification_mutation_detected"


def test_underbound_signed_document_is_not_merge_authority():
    private, root, _ = _keypair()
    underbound = _sign(
        {
            "purpose": SHIPPED_GRAPH_PURPOSE,
            "production_store_mutated": False,
            "rollback_required": True,
            "item_ids": ["edge-1"],
        },
        private,
        root,
    )
    result = verify_shipped_graph_promotion(
        underbound,
        trust_root=root,
        live_context={},
    )
    assert result.ok is False
    assert result.reason == "promotion_schema_fields_mismatch"


def test_v1_promotion_authority_is_not_accepted_by_v3_boundary():
    private, root, _ = _keypair()
    old = _promotion_payload(
        schema_version="atanor.shipped-graph-promotion-document.v1",
        purpose="atanor.shipped-graph-promotion.v1",
    )
    document = _sign(old, private, root)
    assert verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=_live_context(document),
    ).reason == "purpose_mismatch"


@pytest.mark.parametrize(
    "change",
    [
        None,
        True,
        {"schema_version": "atanor.promotion-nonce-replay-domain.v1"},
        {
            "schema_version": "atanor.promotion-nonce-replay-domain.v1",
            "ledger_id": "short",
            "target_store_id": "shipped-graph-primary",
            "resolved_root_sha256": "5" * 64,
            "identity_manifest_sha256": "6" * 64,
            "lock_relative_path": ".shipped-store-promotion.lock",
            "claims_relative_path": "claims",
        },
        {
            "schema_version": "atanor.promotion-nonce-replay-domain.v1",
            "ledger_id": "atanor:promotion-ledger:test-domain-00000001",
            "target_store_id": "shipped-graph-primary",
            "resolved_root_sha256": "A" * 64,
            "identity_manifest_sha256": "6" * 64,
            "lock_relative_path": ".shipped-store-promotion.lock",
            "claims_relative_path": "claims",
        },
    ],
)
def test_nonce_replay_domain_is_strictly_typed_and_bound(change):
    private, root, _ = _keypair()
    document = _sign(
        _promotion_payload(nonce_replay_domain=change),
        private,
        root,
    )
    result = verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=_live_context(document),
    )
    assert result.reason == "nonce_replay_domain_invalid"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"merge_authorized": "true"}, "merge_authority_contract_invalid"),
        ({"production_store_mutated": "false"}, "preverification_mutation_detected"),
        ({"rollback_required": 1}, "rollback_contract_missing"),
        ({"staging_receipt_sha256": "A" * 64}, "staging_receipt_digest_invalid"),
        ({"candidate_digest_sha256": "not-a-digest"}, "candidate_digest_invalid"),
        (
            {"mutation_batch_manifest_sha256": "A" * 64},
            "mutation_batch_manifest_digest_invalid",
        ),
        ({"item_ids": ["edge-1", "edge-2"]}, "item_ids_invalid"),
        ({"item_ids": ["edge-1", "edge-1"]}, "item_ids_invalid"),
        ({"item_ids": "edge-1"}, "item_ids_invalid"),
        ({"target_store_id": "  "}, "target_store_id_invalid"),
        ({"target_store_id": "store\nadmin"}, "target_store_id_invalid"),
        ({"base_revision": ""}, "base_revision_invalid"),
        ({"rollback_artifact_sha256": "4" * 63}, "rollback_artifact_digest_invalid"),
        ({"nonce": "short"}, "nonce_invalid"),
    ],
)
def test_strict_promotion_schema_rejects_truthy_or_malformed_fields(change, reason):
    private, root, _ = _keypair()
    payload = _promotion_payload(**change)
    document = _sign(payload, private, root)
    result = verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=_live_context(document),
    )
    assert result.ok is False
    assert result.reason == reason


def test_signed_document_requires_exact_top_level_and_signature_fields():
    private, root, _ = _keypair()
    with_extra = _sign(_promotion_payload(extra_authority="all-stores"), private, root)
    assert verify_shipped_graph_promotion(
        with_extra,
        trust_root=root,
        live_context=_live_context(with_extra),
    ).reason == "promotion_schema_fields_mismatch"

    signature_extra = _sign(_promotion_payload(), private, root)
    signature_extra[SIGNATURE_FIELD]["unreviewed_scope"] = "all-stores"
    assert verify_shipped_graph_promotion(
        signature_extra,
        trust_root=root,
        live_context=_live_context(signature_extra),
    ).reason == "signature_envelope_fields_mismatch"


@pytest.mark.parametrize(
    "field",
    [
        "staging_receipt_sha256",
        "candidate_digest_sha256",
        "mutation_batch_manifest_sha256",
        "item_ids",
        "target_store_id",
        "operator_boundary_id",
        "operator_boundary_config_sha256",
        "base_revision",
        "rollback_artifact_sha256",
        "nonce_replay_domain",
    ],
)
def test_signed_authorization_must_match_each_live_merge_binding(field):
    private, root, _ = _keypair()
    document = _sign(_promotion_payload(), private, root)
    context = _live_context(document)
    if field == "item_ids":
        context[field] = ["edge-2"]
    elif field == "nonce_replay_domain":
        context[field] = {
            **context[field],
            "resolved_root_sha256": "9" * 64,
        }
    elif field.endswith("sha256"):
        context[field] = "9" * 64
    else:
        context[field] = f"different-{field}"
        if field == "target_store_id":
            context["nonce_replay_domain"] = {
                **context["nonce_replay_domain"],
                "target_store_id": context[field],
            }
    result = verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=context,
    )
    assert result.ok is False
    assert result.reason == f"live_{field}_mismatch"


def test_live_context_is_mandatory_and_exact():
    private, root, _ = _keypair()
    document = _sign(_promotion_payload(), private, root)
    assert verify_shipped_graph_promotion(
        document,
        trust_root=root,
    ).reason == "live_context_required"
    context = _live_context(document)
    context["unreviewed"] = True
    assert verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=context,
    ).reason == "live_context_fields_mismatch"


def test_promotion_authority_is_time_bounded():
    private, root, _ = _keypair()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expired = _sign(
        _promotion_payload(
            issued_at=(now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=(now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        private,
        root,
    )
    assert verify_shipped_graph_promotion(
        expired,
        trust_root=root,
        live_context=_live_context(expired),
    ).reason == "authorization_expired"

    future = _sign(
        _promotion_payload(
            issued_at=(now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=(now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        private,
        root,
    )
    assert verify_shipped_graph_promotion(
        future,
        trust_root=root,
        live_context=_live_context(future),
    ).reason == "authorization_not_yet_valid"


def test_historical_verifier_uses_consumption_time_without_weakening_live_clock():
    private, root, _ = _keypair()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    document = _sign(
        _promotion_payload(
            issued_at=(now - timedelta(minutes=20)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            expires_at=(now - timedelta(minutes=10)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        ),
        private,
        root,
    )
    assert verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=_live_context(document),
    ).reason == "authorization_expired"

    historical = verify_shipped_graph_promotion_historical(
        document,
        trust_root=root,
        live_context=_live_context(document),
        consumption_time=now - timedelta(minutes=15),
    )
    assert historical.ok is True

    outside = verify_shipped_graph_promotion_historical(
        document,
        trust_root=root,
        live_context=_live_context(document),
        consumption_time=now - timedelta(minutes=5),
    )
    assert outside.reason == "authorization_expired"


def test_historical_v2_evidence_remains_readable_but_cannot_authorize_live_swap():
    private, root, _ = _keypair()
    payload = _promotion_payload(
        schema_version="atanor.shipped-graph-promotion-document.v2",
        purpose="atanor.shipped-graph-promotion.v2",
    )
    payload.pop("mutation_batch_manifest_sha256")
    document = _sign(payload, private, root)
    legacy_context = _live_context(
        {
            **document,
            "mutation_batch_manifest_sha256": "0" * 64,
        }
    )
    legacy_context.pop("mutation_batch_manifest_sha256")

    assert verify_shipped_graph_promotion(
        document,
        trust_root=root,
        live_context=legacy_context,
    ).reason == "purpose_mismatch"
    historical = verify_shipped_graph_promotion_historical(
        document,
        trust_root=root,
        live_context=legacy_context,
        consumption_time=datetime.now(timezone.utc),
    )
    assert historical.ok is True


def test_external_loader_rejects_repository_embedded_trust_root(tmp_path):
    _, root, pem = _keypair()
    repo = tmp_path / "repo"
    repo.mkdir()
    key = repo / "operator.pub.pem"
    key.write_bytes(pem)
    with pytest.raises(ValueError, match="outside the repository"):
        OperatorTrustRoot.from_external_file(
            key,
            repository_root=repo,
            expected_key_id=root.key_id,
        )


def test_unpinned_or_wrongly_pinned_key_is_never_accepted():
    _, root, pem = _keypair()
    with pytest.raises(ValueError, match="pin is required"):
        OperatorTrustRoot(pem, expected_key_id="")
    with pytest.raises(ValueError, match="does not match"):
        OperatorTrustRoot(pem, expected_key_id="ed25519:" + "0" * 24)
    assert root.key_id.startswith("ed25519:")
