# -*- coding: utf-8 -*-
"""SEALED GATE (d): an unsigned shipped-graph promotion is REFUSED.

A shipped-graph write is never autonomous: the envelope queues it and denies auto-apply.
Staging requires the exact operator phrase + literal confirmed flag; without both it is refused.
Even a confirmed batch produces only an unsigned receipt — production is never mutated.
"""
from __future__ import annotations

import hashlib

from packages.autonomy_envelope import (
    ActionKind,
    AutonomyEnvelope,
    EnvelopeAction,
    REQUIRED_CONFIRMATION_PHRASE,
)


def test_shipped_write_is_never_auto_applied_but_queued(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    dec = env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship edge france-capital-paris",
                                   {"item_id": "edge_42"}))
    assert dec.allowed is False, "a shipped-graph write must never be auto-allowed"
    assert "operator signature" in dec.reason
    # ... but it IS queued for the morning
    assert env.promotions.pending_count() == 1
    pending = env.promotions.pending()
    assert pending[0]["item_id"] == "edge_42"
    assert pending[0]["production_store_mutated"] is False


def test_sign_refused_without_confirmation(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship", {"item_id": "e1"}))

    # not confirmed, no phrase
    r = env.sign_promotion_batch(operator_confirmed=False, confirmation_phrase="")
    assert r["allowed"] is False
    assert "operator_confirmation_required" in r["reasons"]
    assert "required_phrase_mismatch" in r["reasons"]
    assert r["signed"] is False
    # still pending, nothing applied
    assert env.promotions.pending_count() == 1


def test_sign_refused_with_wrong_phrase(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship", {"item_id": "e1"}))
    r = env.sign_promotion_batch(operator_confirmed=True, confirmation_phrase="please ship it")
    assert r["allowed"] is False
    assert "required_phrase_mismatch" in r["reasons"]
    assert env.promotions.pending_count() == 1


def test_truthy_confirmation_value_is_not_operator_authority(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship", {"item_id": "e1"}))
    r = env.sign_promotion_batch(
        operator_confirmed="false",
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
    )
    assert r["allowed"] is False
    assert r["signed"] is False
    assert "operator_confirmation_required" in r["reasons"]
    assert env.promotions.pending_count() == 1


def test_sign_refused_when_nothing_pending(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    r = env.sign_promotion_batch(operator_confirmed=True,
                                 confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE)
    assert r["allowed"] is False
    assert "no_pending_promotions" in r["reasons"]


def test_graph_candidate_confirmation_requires_a_sealed_mutation_batch(
    tmp_path,
):
    env = AutonomyEnvelope(tmp_path)
    env.promotions.queue(
        {
            "item_id": "graph-candidate-1",
            "promotion_kind": "graph_store_candidate",
            "candidate_digest_sha256": "a" * 64,
        }
    )
    refused = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
    )
    assert refused["allowed"] is False
    assert refused["reasons"] == [
        "mutation_batch_manifest_digest_invalid"
    ]
    assert env.promotions.pending_count() == 1


def test_graph_candidate_confirmation_binds_mutation_manifest_hash(
    tmp_path,
):
    env = AutonomyEnvelope(tmp_path)
    manifest_sha256 = "b" * 64
    env.promotions.queue(
        {
            "item_id": "graph-candidate-1",
            "promotion_kind": "graph_store_candidate",
            "candidate_digest_sha256": "a" * 64,
            "mutation_batch_manifest_sha256": manifest_sha256,
        }
    )
    result = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
    )
    assert result["allowed"] is True
    from pathlib import Path
    import json

    receipt = json.loads(
        Path(result["manifest_path"]).read_text(encoding="utf-8")
    )
    assert (
        receipt["entries"][0]["payload"][
            "mutation_batch_manifest_sha256"
        ]
        == manifest_sha256
    )


def test_exact_confirmation_requires_one_selected_item_and_never_mutates_shipped_store(
    tmp_path,
):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e1", {"item_id": "e1"}))
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e2", {"item_id": "e2"}))
    assert env.promotions.pending_count() == 2

    ambiguous = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="blueyjkim",
    )
    assert ambiguous["allowed"] is False
    assert ambiguous["reasons"] == [
        "single_promotion_selection_required"
    ]

    r = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="blueyjkim",
        item_id="e2",
    )
    assert r["allowed"] is True and r["staging_allowed"] is True
    assert r["signed"] is False
    # the crucial invariant: signing stages a manifest, it does NOT write the shipped graph
    assert r["production_store_mutated"] is False
    assert r["shipped_graph_write"] is False
    assert r["cryptographically_signed"] is False
    assert r["merge_authorized"] is False
    assert r["authorization_scope"] == "staging_only"
    assert r["attestation_level"] == "interactive_confirmation"
    assert r["item_count"] == 1
    assert r["item_ids"] == ["e2"]
    # an unsigned staging receipt exists on disk
    from pathlib import Path

    receipt = Path(r["manifest_path"])
    assert receipt.exists()
    assert r["staging_receipt_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    # Confirmation cannot consume work awaiting real cryptographic authorization.
    assert env.promotions.pending_count() == 2
    staged_event = env.ledger.events_of("batch_confirmed_staged")[-1]
    assert (
        staged_event["payload"]["staging_receipt_sha256"]
        == r["staging_receipt_sha256"]
    )


def test_repeated_confirmation_refuses_collision_and_never_trusts_existing_receipt(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e1", {"item_id": "e1"}))
    first = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="operator-1",
    )
    from pathlib import Path

    receipt = Path(first["manifest_path"])
    original = receipt.read_bytes()
    second = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="operator-1",
    )
    assert second["allowed"] is False
    assert second["staging_allowed"] is False
    assert second["signed"] is False
    assert second["manifest_path"] is None
    assert second["reasons"] == ["staging_receipt_collision"]
    assert receipt.read_bytes() == original
    assert env.promotions.pending_count() == 1


def test_duplicate_nomination_cannot_poison_an_unrelated_explicit_selection(
    tmp_path,
):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e1a", {"item_id": "e1"}))
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e1b", {"item_id": "e1"}))
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e2", {"item_id": "e2"}))

    selected = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        item_id="e2",
    )
    assert selected["allowed"] is True
    assert selected["item_ids"] == ["e2"]

    ambiguous = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        item_id="e1",
    )
    assert ambiguous["allowed"] is False
    assert ambiguous["reasons"] == [
        "promotion_item_not_found_or_ambiguous"
    ]


def test_edited_existing_receipt_cannot_inject_authority_into_return_value(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship e1", {"item_id": "e1"}))
    first = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="operator-1",
    )
    from pathlib import Path
    import json

    receipt = Path(first["manifest_path"])
    edited = json.loads(receipt.read_text(encoding="utf-8"))
    edited["merge_authorized"] = True
    edited["cryptographically_signed"] = True
    receipt.write_text(json.dumps(edited), encoding="utf-8")

    second = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="operator-1",
    )
    assert second["allowed"] is False
    assert second["merge_authorized"] is False
    assert second["cryptographically_signed"] is False
    assert second["manifest_path"] is None
    assert env.ledger.events_of("batch_confirmation_refused")[-1]["payload"] == {
        "reason": "staging_receipt_collision",
        "batch_id": first["batch_id"],
    }


def test_malformed_phrase_or_operator_id_fails_closed(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship", {"item_id": "e1"}))
    result = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase={"phrase": REQUIRED_CONFIRMATION_PHRASE},
        operator_id=False,
    )
    assert result["allowed"] is False
    assert "required_phrase_mismatch" in result["reasons"]
    assert "operator_id_invalid" in result["reasons"]


def test_refusal_is_audit_logged(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship", {"item_id": "e1"}))
    env.sign_promotion_batch(operator_confirmed=False, confirmation_phrase="")
    assert env.ledger.events_of("batch_sign_refused"), "a refused signature must be logged"
