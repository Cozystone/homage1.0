from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from packages.cognitive_core import (
    CO_F1_PROFILE_SCHEMA,
    ClaimEnvelope,
    CognitiveEnvelope,
    CognitiveMoment,
    EpistemicTier,
    GoalIR,
    GoalOrigin,
    WorldSnapshot,
    adapt_co_f1_profile_receipt,
    build_co_f1_profile,
)


SLOTS = (
    "attention_salience",
    "drive_compute",
    "epistemic_confidence",
    "external_action_proposal",
    "grounding",
    "hormone_resource",
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _available(namespace: str, label: str, *, sampled_at_ns: int = 900):
    return {
        "namespace": namespace,
        "state": "available",
        "instance_id": f"{namespace}:instance",
        "revision": f"{namespace}:revision",
        "sampled_at_ns": sampled_at_ns,
        "max_age_ns": 200,
        "payload_sha256": _digest(label),
    }


def _slot_sources():
    return {
        "attention_salience": [_available("attention.source", "attention")],
        "drive_compute": [_available("drive.source", "drive")],
        "epistemic_confidence": [_available("claim.source", "claim")],
        "external_action_proposal": [],
        "grounding": [_available("grounding.source", "grounding")],
        "hormone_resource": [
            _available("hormone.source", "hormone"),
            _available("resource.source", "resource"),
        ],
    }


def _contracts(
    *,
    hormone_signals=None,
    resource_state=None,
    moment_metadata=None,
    reverse_goals: bool = False,
    select_intrinsic: bool = False,
):
    explicit = GoalIR(
        statement="Preserve the operator-approved user task.",
        origin=GoalOrigin.EXPLICIT_USER,
        priority=0,
    )
    intrinsic = GoalIR(
        statement="Explore an interesting alternative.",
        origin=GoalOrigin.INTRINSIC,
        priority=100,
    )
    claim = ClaimEnvelope(
        statement="The bounded fixture produced a candidate.",
        tier=EpistemicTier.INFERRED,
        confidence=0.71,
    )
    world = WorldSnapshot(
        world_time="logical:f1",
        snapshot_index=1,
        inferred_claim_ids=(claim.contract_id,),
    )
    envelope = CognitiveEnvelope(
        session_id="session:co-f1",
        explicit_user_goal_ids=(explicit.contract_id,),
        intrinsic_goal_ids=(intrinsic.contract_id,),
        world_snapshot_id=world.contract_id,
        hormone_signals=hormone_signals or {"cortisol": 0.2},
    )
    ordered = (
        (intrinsic.contract_id, explicit.contract_id)
        if reverse_goals
        else (explicit.contract_id, intrinsic.contract_id)
    )
    moment = CognitiveMoment(
        moment_index=7,
        envelope_id=envelope.contract_id,
        world_snapshot_id=world.contract_id,
        active_goal_ids=ordered,
        selected_goal_id=intrinsic.contract_id if select_intrinsic else None,
        claim_ids=(claim.contract_id,),
        attention_targets=("goal:user", "goal:intrinsic"),
        hormone_signals=envelope.hormone_signals,
        resource_state=resource_state or {"tokens_remaining": 128},
        metadata=moment_metadata or {},
    )
    return envelope, (explicit, intrinsic), world, (claim,), moment


def _build(*, slot_sources=None, **contract_kwargs):
    envelope, goals, world, claims, moment = _contracts(**contract_kwargs)
    receipt = build_co_f1_profile(
        envelope=envelope,
        goals=goals,
        world_snapshot=world,
        claims=claims,
        moment=moment,
        slot_sources=slot_sources or _slot_sources(),
        read_at_ns=1_000,
    )
    return envelope, goals, world, claims, moment, receipt


def test_same_f1_input_has_identical_canonical_receipt():
    envelope, goals, world, claims, moment, first = _build()
    reordered = _slot_sources()
    reordered["hormone_resource"] = list(reversed(reordered["hormone_resource"]))
    second = build_co_f1_profile(
        envelope=envelope,
        goals=tuple(reversed(goals)),
        world_snapshot=world,
        claims=tuple(reversed(claims)),
        moment=moment,
        slot_sources={key: reordered[key] for key in reversed(SLOTS)},
        read_at_ns=1_000,
    )
    assert first.contract_id == second.contract_id
    assert first.to_dict() == second.to_dict()
    adapted = adapt_co_f1_profile_receipt(
        first.to_dict(),
        envelope=envelope,
        goals=goals,
        world_snapshot=world,
        claims=claims,
        moment=moment,
    )
    assert adapted.to_dict() == first.to_dict()


def test_every_advisory_channel_is_bound_to_its_own_source_and_grounding_exists():
    _, _, _, _, _, receipt = _build()
    metadata = receipt.metadata.to_dict()
    profiles = metadata["slot_profiles"]
    assert set(profiles) == set(SLOTS)
    assert profiles["epistemic_confidence"]["domain"] == "epistemic"
    assert profiles["grounding"]["domain"] == "grounding"
    assert profiles["attention_salience"]["domain"] == "attention"
    assert profiles["drive_compute"]["effect"] == "compute_advisory_only"
    assert profiles["external_action_proposal"]["sources"] == []
    assert profiles["external_action_proposal"]["effect"] == "proposal_only_no_authority"
    assert metadata["profile_status"] == "fresh"
    assert metadata["profile_freshness_complete"] is True
    assert metadata["observation_join_claimed"] is False
    assert metadata["co_profile_schema"] == CO_F1_PROFILE_SCHEMA


def test_missing_stale_and_unversioned_sources_remain_explicit_and_fail_closed():
    sources = _slot_sources()
    sources["grounding"] = [
        {
            "namespace": "grounding.source",
            "state": "missing",
            "reason_code": "not_wired",
        }
    ]
    sources["attention_salience"] = [
        _available("attention.source", "attention", sampled_at_ns=700)
    ]
    sources["drive_compute"] = [
        {
            "namespace": "drive.source",
            "state": "unversioned",
            "instance_id": "drive.source:instance",
            "reason_code": "revision_absent",
        }
    ]
    _, _, _, _, _, receipt = _build(slot_sources=sources)
    metadata = receipt.metadata.to_dict()
    profiles = metadata["slot_profiles"]
    assert profiles["grounding"]["sources"][0]["freshness"] == "missing"
    assert profiles["grounding"]["sources"][0]["payload_sha256"] is None
    assert profiles["attention_salience"]["sources"][0]["freshness"] == "stale"
    assert profiles["attention_salience"]["sources"][0]["age_ns"] == 300
    assert profiles["drive_compute"]["sources"][0]["freshness"] == "unversioned"
    assert metadata["profile_status"] == "degraded_fail_closed"
    assert metadata["profile_freshness_complete"] is False
    assert set(metadata["unusable_slots"]) == {
        "attention_salience",
        "drive_compute",
        "grounding",
    }


def test_unavailable_source_is_explicit_and_cannot_smuggle_raw_payload():
    sources = _slot_sources()
    sources["grounding"] = [
        {
            "namespace": "grounding.source",
            "state": "unavailable",
            "reason_code": "source_offline",
        }
    ]
    _, _, _, _, _, receipt = _build(slot_sources=sources)
    source = receipt.metadata.to_dict()["slot_profiles"]["grounding"]["sources"][0]
    assert source["state"] == source["freshness"] == "unavailable"
    assert source["reason_code"] == "source_offline"
    assert source["payload_sha256"] is None
    assert receipt.metadata["profile_status"] == "degraded_fail_closed"

    sources = _slot_sources()
    sources["grounding"][0]["payload"] = {"secret": "raw-organ-value"}
    with pytest.raises(ValueError, match="unexpected fields"):
        _build(slot_sources=sources)


def test_slot_provenance_separates_attention_epistemic_metabolic_and_authority_hashes():
    _, _, _, _, _, base = _build()
    attention_sources = _slot_sources()
    attention_sources["attention_salience"] = [
        _available("attention.source", "different-attention")
    ]
    _, _, _, _, _, attention = _build(slot_sources=attention_sources)
    _, _, _, _, _, metabolic = _build(
        hormone_signals={"cortisol": 0.8},
        resource_state={"tokens_remaining": 32},
    )
    base_hashes = base.metadata.to_dict()["domain_hashes"]
    attention_hashes = attention.metadata.to_dict()["domain_hashes"]
    metabolic_hashes = metabolic.metadata.to_dict()["domain_hashes"]
    assert attention_hashes["attention"] != base_hashes["attention"]
    assert attention_hashes["epistemic"] == base_hashes["epistemic"]
    assert attention_hashes["authority"] == base_hashes["authority"]
    assert metabolic_hashes["metabolic_resource"] != base_hashes["metabolic_resource"]
    assert metabolic_hashes["epistemic"] == base_hashes["epistemic"]
    assert metabolic_hashes["authority"] == base_hashes["authority"]


def test_receipt_is_profile_only_with_fixed_empty_authority_and_action():
    _, _, _, _, _, receipt = _build()
    fence = receipt.metadata.to_dict()["authority_fence"]
    assert fence["authority_grants"] == []
    assert all(
        fence[key] is False
        for key in (
            "action_authority",
            "evaluator_feedback_authority",
            "moral_mutation_allowed",
            "operator_identity_override_allowed",
            "permission_mutation_allowed",
            "promotion_authority",
            "safety_mutation_allowed",
            "truth_mutation_allowed",
        )
    )
    assert receipt.proposed_action.to_dict() == {}
    assert receipt.selected_goal_id is None
    assert receipt.authoritative is False
    assert receipt.action_executed is False


def test_explicit_goal_order_is_required_and_intrinsic_selection_is_rejected():
    envelope, goals, world, claims, moment = _contracts(reverse_goals=True)
    with pytest.raises(ValueError, match="explicit-before-intrinsic"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )
    envelope, goals, world, claims, moment = _contracts(select_intrinsic=True)
    with pytest.raises(ValueError, match="intrinsic goal cannot be selected"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )


@pytest.mark.parametrize(
    ("channel", "signals"),
    (
        ("hormone", {"moral_override": 1.0}),
        ("hormone", {"promotion_score": 1.0}),
        ("resource", {"evaluator_budget": 1.0}),
        ("resource", {"operator_identity": 1.0}),
    ),
)
def test_f1_rejects_extended_authority_controls_in_hormone_and_resource_channels(
    channel,
    signals,
):
    kwargs = (
        {"hormone_signals": signals}
        if channel == "hormone"
        else {"resource_state": signals}
    )
    envelope, goals, world, claims, moment = _contracts(**kwargs)
    with pytest.raises(ValueError, match="reserved authority controls"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )


def test_source_schema_rejects_unknown_fields_duplicates_and_action_binding():
    sources = _slot_sources()
    sources["grounding"][0]["permission_authority"] = True
    with pytest.raises(ValueError, match="unexpected fields"):
        _build(slot_sources=sources)

    sources = _slot_sources()
    sources["grounding"].append(dict(sources["grounding"][0]))
    with pytest.raises(ValueError, match="duplicate source bindings"):
        _build(slot_sources=sources)

    sources = _slot_sources()
    sources["external_action_proposal"] = [_available("action.source", "action")]
    with pytest.raises(ValueError, match="must remain empty"):
        _build(slot_sources=sources)


@pytest.mark.parametrize("bad_time", (True, -1))
def test_source_time_rejects_boolean_or_negative_values(bad_time):
    sources = _slot_sources()
    sources["grounding"][0]["sampled_at_ns"] = bad_time
    with pytest.raises((TypeError, ValueError)):
        _build(slot_sources=sources)


def test_future_source_is_rejected_and_freshness_boundary_is_inclusive():
    sources = _slot_sources()
    sources["grounding"][0]["sampled_at_ns"] = 1_001
    with pytest.raises(ValueError, match="future-dated"):
        _build(slot_sources=sources)

    sources = _slot_sources()
    sources["grounding"][0]["sampled_at_ns"] = 800
    _, _, _, _, _, receipt = _build(slot_sources=sources)
    source = receipt.metadata.to_dict()["slot_profiles"]["grounding"]["sources"][0]
    assert source["age_ns"] == source["max_age_ns"] == 200
    assert source["freshness"] == "fresh"


def test_profile_refuses_live_join_metadata_and_cross_moment_masquerade():
    envelope, goals, world, claims, moment = _contracts(
        moment_metadata={"live_candidate": "not_f1"}
    )
    with pytest.raises(ValueError, match="live join metadata"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )

    envelope, goals, world, claims, moment, receipt = _build()
    (
        other_envelope,
        other_goals,
        other_world,
        other_claims,
        other_moment,
    ) = _contracts(
        resource_state={"tokens_remaining": 64}
    )
    with pytest.raises(ValueError, match="not bound"):
        adapt_co_f1_profile_receipt(
            receipt,
            envelope=other_envelope,
            goals=other_goals,
            world_snapshot=other_world,
            claims=other_claims,
            moment=other_moment,
        )


def test_profile_requires_substantiated_claims_and_canonical_goals():
    envelope, goals, world, claims, moment = _contracts()
    with pytest.raises(ValueError, match="exactly substantiate"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=(),
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )

    object.__setattr__(goals[0], "statement", "Tampered after canonical sealing.")
    with pytest.raises(ValueError, match="canonical identity"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )


def test_profile_rejects_extra_authority_attributes_on_typed_inputs():
    envelope, goals, world, claims, moment = _contracts()
    object.__setattr__(envelope, "permission_grant", True)
    with pytest.raises(ValueError, match="exact canonical contract instance field set"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )


def test_profile_rejects_an_unversioned_envelope_to_moment_hormone_change():
    envelope, goals, world, claims, moment = _contracts()
    changed_moment = replace(moment, hormone_signals={"cortisol": 0.8})
    with pytest.raises(ValueError, match="hormone signals do not match"):
        build_co_f1_profile(
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=changed_moment,
            slot_sources=_slot_sources(),
            read_at_ns=1_000,
        )


def test_strict_adapter_rejects_tampered_or_masquerading_receipt():
    envelope, goals, world, claims, moment, receipt = _build()
    payload = receipt.to_dict()
    payload["metadata"]["profile_status"] = "degraded_fail_closed"
    with pytest.raises(ValueError):
        adapt_co_f1_profile_receipt(
            payload,
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
        )

    payload = receipt.to_dict()
    payload["permission_grant"] = True
    with pytest.raises(ValueError, match="exact canonical field set"):
        adapt_co_f1_profile_receipt(
            payload,
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
        )

    object.__setattr__(receipt, "permission_grant", True)
    with pytest.raises(ValueError, match="exact canonical instance field set"):
        adapt_co_f1_profile_receipt(
            receipt,
            envelope=envelope,
            goals=goals,
            world_snapshot=world,
            claims=claims,
            moment=moment,
        )
