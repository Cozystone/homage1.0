"""CO-C0 F1 authority, provenance, and freshness profile.

F1 is deliberately only a pure profile over the existing cognitive contracts.
It creates no state owner, ledger, daemon, organ, clock read, model call, tool
call, or live join.  The caller supplies an existing envelope, goals, world
snapshot, claims, ``CognitiveMoment``, and source stamps; this module returns
an ordinary shadow ``DecisionReceipt``.

Every channel is bound through a closed slot-to-domain map.  Source stamps
carry identifiers, revisions, times, TTLs, and payload hashes only--never raw
organ values.  Missing, unavailable, unversioned, stale, and future-dated
inputs cannot silently become neutral telemetry.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from packages.cognitive_core.adapters import (
    adapt_claim_envelope,
    adapt_cognitive_envelope,
    adapt_cognitive_moment,
    adapt_decision_receipt,
    adapt_goal_ir,
    adapt_world_snapshot,
)
from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.cognitive_core.contracts import (
    ClaimEnvelope,
    CognitiveEnvelope,
    CognitiveMoment,
    DecisionReceipt,
    EpistemicTier,
    GoalIR,
    GoalOrigin,
    ReceiptMode,
    WorldSnapshot,
    order_goals_for_deliberation,
)


CO_F1_PROFILE_SCHEMA = "atanor.cognitive_core.co-c0.f1.v1"

_DECISION_KIND = "co_f1_authority_source_freshness_profile"
_RATIONALE = (
    "This contract-only profile grants no truth, moral, safety, permission, "
    "evaluator, promotion, operator-identity, or action authority."
)
_SOURCE_STATES = frozenset({"available", "missing", "unavailable", "unversioned"})
_SOURCE_INPUT_FIELDS = frozenset(
    {
        "instance_id",
        "max_age_ns",
        "namespace",
        "payload_sha256",
        "reason_code",
        "revision",
        "sampled_at_ns",
        "state",
    }
)
_NORMALIZED_SOURCE_FIELDS = frozenset(
    {
        "age_ns",
        "freshness",
        "instance_id",
        "max_age_ns",
        "payload_sha256",
        "read_at_ns",
        "reason_code",
        "revision",
        "sampled_at_ns",
        "source_namespace",
        "state",
    }
)
_PROFILE_METADATA_FIELDS = frozenset(
    {
        "authority_fence",
        "co_profile_schema",
        "domain_hashes",
        "observation_join_claimed",
        "profile_freshness_complete",
        "profile_scope",
        "profile_status",
        "read_at_ns",
        "reserved_domains",
        "slot_profiles",
        "unusable_slots",
    }
)
_SLOT_PROFILE_FIELDS = frozenset(
    {"domain", "effect", "freshness_eligible_for_declared_role", "sources"}
)
_OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,255}$")
_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,95}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_F1_CONTROL_KEY_PATTERN = re.compile(
    r"(truth|moral|safety|permission|authority|policy|authorize|approve|"
    r"accept_as_fact|evaluator|promotion|operator_(?:identity|id)|"
    r"(?:identity|id)_operator)",
    re.IGNORECASE,
)

_SLOT_POSTURES = FrozenMap(
    {
        "attention_salience": {
            "domain": "attention",
            "effect": "compute_advisory_only",
        },
        "drive_compute": {
            "domain": "compute",
            "effect": "compute_advisory_only",
        },
        "epistemic_confidence": {
            "domain": "epistemic",
            "effect": "evidence_only",
        },
        "external_action_proposal": {
            "domain": "external_action",
            "effect": "proposal_only_no_authority",
        },
        "grounding": {
            "domain": "grounding",
            "effect": "evidence_only",
        },
        "hormone_resource": {
            "domain": "compute",
            "effect": "compute_advisory_only",
        },
    }
)
_ADVISORY_SLOTS = tuple(
    slot for slot in _SLOT_POSTURES if slot != "external_action_proposal"
)
_AUTHORITY_FENCE = FrozenMap(
    {
        "action_authority": False,
        "authority_grants": (),
        "evaluator_promotion_binding": "external_unattested",
        "evaluator_feedback_authority": False,
        "moral_safety_binding": "external_unattested",
        "moral_mutation_allowed": False,
        "operator_identity_binding": "external_unattested",
        "operator_identity_override_allowed": False,
        "permission_mutation_allowed": False,
        "promotion_authority": False,
        "safety_mutation_allowed": False,
        "truth_mutation_allowed": False,
    }
)
_RESERVED_DOMAINS = FrozenMap(
    {
        "evaluator": "external_unattested",
        "moral": "external_unattested",
        "operator_identity": "external_unattested",
        "permission": "external_unattested",
        "promotion": "external_unattested",
        "safety": "external_unattested",
        "truth": "external_unattested",
    }
)
_WORLD_CLAIM_FIELDS = (
    (EpistemicTier.OBSERVED, "observed_claim_ids"),
    (EpistemicTier.RECORDED, "recorded_claim_ids"),
    (EpistemicTier.INFERRED, "inferred_claim_ids"),
    (EpistemicTier.PREDICTED, "predicted_claim_ids"),
    (EpistemicTier.RETRODICTED, "retrodicted_claim_ids"),
)


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _strict_identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a strict opaque identifier")
    return value


def _namespace(value: Any) -> str:
    if not isinstance(value, str) or not _NAMESPACE_PATTERN.fullmatch(value):
        raise ValueError(
            "source namespace must be lowercase and contain only letters, digits, "
            "dot, underscore, colon, or hyphen"
        )
    return value


def _reason(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _REASON_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase reason code")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _validate_typed_contract_instance(
    value: Any,
    *,
    expected_type: type,
    adapter: Any,
    name: str,
) -> None:
    if type(value) is not expected_type:
        raise TypeError(f"{name} must be the canonical {expected_type.__name__} type")
    if not value.verify_identity():
        raise ValueError("F1 input contracts must retain canonical identity")
    rebuilt = adapter(value.to_dict())
    if set(vars(value)) != set(vars(rebuilt)):
        raise ValueError(
            f"{name} must use the exact canonical contract instance field set"
        )


def _normalize_source(
    value: Mapping[str, Any],
    *,
    slot: str,
    read_at_ns: int,
) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError(f"slot {slot} source must be a mapping")
    unexpected = sorted(set(value) - _SOURCE_INPUT_FIELDS)
    if unexpected:
        raise ValueError(f"slot {slot} source has unexpected fields: {unexpected}")
    namespace = _namespace(value.get("namespace"))
    state = value.get("state")
    if state not in _SOURCE_STATES:
        raise ValueError(f"slot {slot} source state must be one of {sorted(_SOURCE_STATES)}")

    if state == "available":
        required = (
            "instance_id",
            "revision",
            "sampled_at_ns",
            "max_age_ns",
            "payload_sha256",
        )
        missing = [name for name in required if value.get(name) is None]
        if missing:
            raise ValueError(
                f"available slot {slot} source is unversioned; missing {missing}"
            )
        if value.get("reason_code") is not None:
            raise ValueError(f"available slot {slot} source cannot carry a reason code")
        instance_id = _strict_identifier(value["instance_id"], f"{slot}.instance_id")
        revision = _strict_identifier(value["revision"], f"{slot}.revision")
        sampled_at_ns = _nonnegative_int(value["sampled_at_ns"], f"{slot}.sampled_at_ns")
        max_age_ns = _nonnegative_int(value["max_age_ns"], f"{slot}.max_age_ns")
        payload_sha256 = _sha256(value["payload_sha256"], f"{slot}.payload_sha256")
        if sampled_at_ns > read_at_ns:
            raise ValueError(f"slot {slot} source is future-dated")
        age_ns = read_at_ns - sampled_at_ns
        freshness = "fresh" if age_ns <= max_age_ns else "stale"
        reason_code = None
    else:
        reason_code = _reason(value.get("reason_code"), f"{slot}.reason_code")
        if state in {"missing", "unavailable"}:
            forbidden = (
                "instance_id",
                "revision",
                "sampled_at_ns",
                "max_age_ns",
                "payload_sha256",
            )
        else:
            forbidden = (
                "revision",
                "sampled_at_ns",
                "max_age_ns",
                "payload_sha256",
            )
        present = [name for name in forbidden if value.get(name) is not None]
        if present:
            raise ValueError(
                f"{state} slot {slot} source cannot bind fields: {present}"
            )
        instance_id = (
            None
            if value.get("instance_id") is None
            else _strict_identifier(value["instance_id"], f"{slot}.instance_id")
        )
        revision = None
        sampled_at_ns = None
        max_age_ns = None
        payload_sha256 = None
        age_ns = None
        freshness = state

    return FrozenMap(
        {
            "age_ns": age_ns,
            "freshness": freshness,
            "instance_id": instance_id,
            "max_age_ns": max_age_ns,
            "payload_sha256": payload_sha256,
            "read_at_ns": read_at_ns,
            "reason_code": reason_code,
            "revision": revision,
            "sampled_at_ns": sampled_at_ns,
            "source_namespace": namespace,
            "state": state,
        }
    )


def _normalize_slot_profiles(
    slot_sources: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    read_at_ns: int,
) -> FrozenMap:
    if not isinstance(slot_sources, Mapping):
        raise TypeError("slot_sources must be a mapping")
    if set(slot_sources) != set(_SLOT_POSTURES):
        missing = sorted(set(_SLOT_POSTURES) - set(slot_sources))
        extra = sorted(set(slot_sources) - set(_SLOT_POSTURES))
        raise ValueError(f"slot_sources must match the closed F1 slots; missing={missing}, extra={extra}")

    profiles: dict[str, Any] = {}
    for slot in _SLOT_POSTURES:
        raw_sources = slot_sources[slot]
        if isinstance(raw_sources, (str, bytes)) or not isinstance(raw_sources, Sequence):
            raise TypeError(f"slot {slot} sources must be a sequence")
        if slot == "external_action_proposal":
            if raw_sources:
                raise ValueError("F1 external action proposal slot must remain empty")
            normalized_sources: tuple[FrozenMap, ...] = ()
            eligible = False
        else:
            if not raw_sources:
                raise ValueError(f"slot {slot} must explicitly declare at least one source state")
            source_values = [
                _normalize_source(source, slot=slot, read_at_ns=read_at_ns)
                for source in raw_sources
            ]
            source_values.sort(
                key=lambda source: (
                    source["source_namespace"],
                    source["instance_id"] or "",
                    source["revision"] or "",
                    source["state"],
                )
            )
            identities = [
                (
                    source["source_namespace"],
                    source["instance_id"],
                    source["revision"],
                    source["state"],
                )
                for source in source_values
            ]
            if len(set(identities)) != len(identities):
                raise ValueError(f"slot {slot} contains duplicate source bindings")
            normalized_sources = tuple(source_values)
            eligible = all(source["freshness"] == "fresh" for source in normalized_sources)
        posture = _SLOT_POSTURES[slot]
        profiles[slot] = {
            "domain": posture["domain"],
            "effect": posture["effect"],
            "freshness_eligible_for_declared_role": eligible,
            "sources": normalized_sources,
        }
    return FrozenMap(profiles)


def _validate_moment(
    *,
    envelope: CognitiveEnvelope,
    goals: Sequence[GoalIR],
    world_snapshot: WorldSnapshot,
    claims: Sequence[ClaimEnvelope],
    moment: CognitiveMoment,
) -> None:
    if isinstance(goals, (str, bytes)) or not isinstance(goals, Sequence):
        raise TypeError("goals must be a sequence")
    if isinstance(claims, (str, bytes)) or not isinstance(claims, Sequence):
        raise TypeError("claims must be a sequence")
    _validate_typed_contract_instance(
        envelope,
        expected_type=CognitiveEnvelope,
        adapter=adapt_cognitive_envelope,
        name="envelope",
    )
    _validate_typed_contract_instance(
        world_snapshot,
        expected_type=WorldSnapshot,
        adapter=adapt_world_snapshot,
        name="world_snapshot",
    )
    _validate_typed_contract_instance(
        moment,
        expected_type=CognitiveMoment,
        adapter=adapt_cognitive_moment,
        name="moment",
    )
    for index, goal in enumerate(goals):
        _validate_typed_contract_instance(
            goal,
            expected_type=GoalIR,
            adapter=adapt_goal_ir,
            name=f"goals[{index}]",
        )
    for index, claim in enumerate(claims):
        _validate_typed_contract_instance(
            claim,
            expected_type=ClaimEnvelope,
            adapter=adapt_claim_envelope,
            name=f"claims[{index}]",
        )
    if moment.envelope_id != envelope.contract_id:
        raise ValueError("moment is not bound to the supplied envelope")
    if envelope.world_snapshot_id is None or moment.world_snapshot_id != envelope.world_snapshot_id:
        raise ValueError("moment and envelope must share an explicit world snapshot")
    if world_snapshot.contract_id != envelope.world_snapshot_id:
        raise ValueError("world snapshot is not bound to the supplied envelope and moment")
    if moment.hormone_signals != envelope.hormone_signals:
        raise ValueError("moment hormone signals do not match the supplied envelope")
    if moment.metadata:
        raise ValueError("F1 requires an unextended moment; live join metadata is not in scope")
    if (
        moment.truth_mutation_allowed
        or moment.safety_mutation_allowed
        or moment.permission_mutation_allowed
        or moment.action_authority
    ):
        raise ValueError("F1 moment cannot carry truth, safety, permission, or action authority")

    goal_ids = tuple(goal.contract_id for goal in goals)
    if len(set(goal_ids)) != len(goal_ids):
        raise ValueError("goals cannot contain duplicate contract IDs")
    if set(goal_ids) != set(envelope.deliberation_goal_ids):
        raise ValueError("goals must exactly match the envelope goal IDs")
    explicit = set(envelope.explicit_user_goal_ids)
    intrinsic = set(envelope.intrinsic_goal_ids)
    for goal in goals:
        if goal.contract_id in explicit and goal.origin is not GoalOrigin.EXPLICIT_USER:
            raise ValueError("explicit envelope goal has a non-explicit origin")
        if goal.contract_id in intrinsic and goal.origin is not GoalOrigin.INTRINSIC:
            raise ValueError("intrinsic envelope goal has a non-intrinsic origin")
    ordered_ids = tuple(goal.contract_id for goal in order_goals_for_deliberation(goals))
    if moment.active_goal_ids != ordered_ids:
        raise ValueError("moment goals do not preserve explicit-before-intrinsic order")
    if moment.selected_goal_id in intrinsic and explicit:
        raise ValueError("an intrinsic goal cannot be selected while an explicit user goal is active")

    claim_ids = tuple(claim.contract_id for claim in claims)
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("claims cannot contain duplicate contract IDs")
    if set(claim_ids) != set(moment.claim_ids):
        raise ValueError("claims must exactly substantiate the moment claim IDs")
    world_tiers = {
        claim_id: tier
        for tier, field_name in _WORLD_CLAIM_FIELDS
        for claim_id in getattr(world_snapshot, field_name)
    }
    for claim in claims:
        if world_tiers.get(claim.contract_id) is not claim.tier:
            raise ValueError(
                "each moment claim must be present in the matching world epistemic tier"
            )
    for target in moment.attention_targets:
        if _F1_CONTROL_KEY_PATTERN.search(target):
            raise ValueError("attention targets cannot carry authority or policy controls")
    for channel_name, channel in (
        ("hormone_signals", moment.hormone_signals),
        ("resource_state", moment.resource_state),
    ):
        for key in channel:
            if _F1_CONTROL_KEY_PATTERN.search(key):
                raise ValueError(
                    f"{channel_name} cannot carry F1 reserved authority controls"
                )


def _domain_hashes(moment: CognitiveMoment, slot_profiles: FrozenMap) -> FrozenMap:
    return FrozenMap(
        {
            "attention": canonical_digest(
                {
                    "attention_targets": moment.attention_targets,
                    "slot": slot_profiles["attention_salience"],
                }
            ),
            "authority": canonical_digest(_AUTHORITY_FENCE),
            "compute": canonical_digest(slot_profiles["drive_compute"]),
            "epistemic": canonical_digest(
                {
                    "claim_ids": moment.claim_ids,
                    "slot": slot_profiles["epistemic_confidence"],
                }
            ),
            "external_action": canonical_digest(
                slot_profiles["external_action_proposal"]
            ),
            "grounding": canonical_digest(slot_profiles["grounding"]),
            "metabolic_resource": canonical_digest(
                {
                    "hormone_signals": moment.hormone_signals,
                    "resource_state": moment.resource_state,
                    "slot": slot_profiles["hormone_resource"],
                }
            ),
        }
    )


def _profile_metadata(
    *,
    moment: CognitiveMoment,
    slot_profiles: FrozenMap,
    read_at_ns: int,
) -> FrozenMap:
    unusable = tuple(
        slot
        for slot in _ADVISORY_SLOTS
        if not slot_profiles[slot]["freshness_eligible_for_declared_role"]
    )
    complete = not unusable
    return FrozenMap(
        {
            "authority_fence": _AUTHORITY_FENCE,
            "co_profile_schema": CO_F1_PROFILE_SCHEMA,
            "domain_hashes": _domain_hashes(moment, slot_profiles),
            "observation_join_claimed": False,
            "profile_freshness_complete": complete,
            "profile_scope": "contract_profile_only_not_live_join",
            "profile_status": "fresh" if complete else "degraded_fail_closed",
            "read_at_ns": read_at_ns,
            "reserved_domains": _RESERVED_DOMAINS,
            "slot_profiles": slot_profiles,
            "unusable_slots": unusable,
        }
    )


def _validate_normalized_profiles(slot_profiles: Any, *, read_at_ns: int) -> FrozenMap:
    if not isinstance(slot_profiles, Mapping) or set(slot_profiles) != set(_SLOT_POSTURES):
        raise ValueError("receipt slot profiles do not match the closed F1 slots")
    reconstructed: dict[str, Any] = {}
    for slot in _SLOT_POSTURES:
        profile = slot_profiles[slot]
        if not isinstance(profile, Mapping) or set(profile) != _SLOT_PROFILE_FIELDS:
            raise ValueError(f"receipt slot {slot} does not match the closed profile schema")
        posture = _SLOT_POSTURES[slot]
        if profile["domain"] != posture["domain"] or profile["effect"] != posture["effect"]:
            raise ValueError(f"receipt slot {slot} posture is not canonical")
        sources = profile["sources"]
        if isinstance(sources, (str, bytes)) or not isinstance(sources, Sequence):
            raise ValueError(f"receipt slot {slot} sources must be a sequence")
        if slot == "external_action_proposal":
            if sources or profile["freshness_eligible_for_declared_role"] is not False:
                raise ValueError("receipt F1 action slot must remain empty and advisory-ineligible")
            reconstructed[slot] = {
                "domain": posture["domain"],
                "effect": posture["effect"],
                "freshness_eligible_for_declared_role": False,
                "sources": (),
            }
            continue
        if not sources:
            raise ValueError(f"receipt slot {slot} must declare source missingness")
        normalized_sources: list[FrozenMap] = []
        for source in sources:
            if not isinstance(source, Mapping) or set(source) != _NORMALIZED_SOURCE_FIELDS:
                raise ValueError(f"receipt slot {slot} has a malformed source stamp")
            if source["read_at_ns"] != read_at_ns:
                raise ValueError(f"receipt slot {slot} source read boundary mismatch")
            state = source["state"]
            raw: dict[str, Any] = {
                "namespace": source["source_namespace"],
                "state": state,
            }
            if state == "available":
                raw.update(
                    {
                        "instance_id": source["instance_id"],
                        "revision": source["revision"],
                        "sampled_at_ns": source["sampled_at_ns"],
                        "max_age_ns": source["max_age_ns"],
                        "payload_sha256": source["payload_sha256"],
                    }
                )
            else:
                raw["reason_code"] = source["reason_code"]
                if state == "unversioned" and source["instance_id"] is not None:
                    raw["instance_id"] = source["instance_id"]
            rebuilt = _normalize_source(raw, slot=slot, read_at_ns=read_at_ns)
            if rebuilt.to_dict() != dict(source):
                raise ValueError(f"receipt slot {slot} source freshness is inconsistent")
            normalized_sources.append(rebuilt)
        normalized_sources.sort(
            key=lambda source: (
                source["source_namespace"],
                source["instance_id"] or "",
                source["revision"] or "",
                source["state"],
            )
        )
        identities = [
            (
                source["source_namespace"],
                source["instance_id"],
                source["revision"],
                source["state"],
            )
            for source in normalized_sources
        ]
        if len(set(identities)) != len(identities):
            raise ValueError(f"receipt slot {slot} contains duplicate source bindings")
        eligible = all(source["freshness"] == "fresh" for source in normalized_sources)
        if profile["freshness_eligible_for_declared_role"] is not eligible:
            raise ValueError(f"receipt slot {slot} freshness eligibility is inconsistent")
        reconstructed[slot] = {
            "domain": posture["domain"],
            "effect": posture["effect"],
            "freshness_eligible_for_declared_role": eligible,
            "sources": tuple(normalized_sources),
        }
    return FrozenMap(reconstructed)


def build_co_f1_profile(
    *,
    envelope: CognitiveEnvelope,
    goals: Sequence[GoalIR],
    world_snapshot: WorldSnapshot,
    claims: Sequence[ClaimEnvelope],
    moment: CognitiveMoment,
    slot_sources: Mapping[str, Sequence[Mapping[str, Any]]],
    read_at_ns: int,
) -> DecisionReceipt:
    """Return one strict, shadow-only F1 receipt over an existing moment."""

    normalized_read_at_ns = _nonnegative_int(read_at_ns, "read_at_ns")
    _validate_moment(
        envelope=envelope,
        goals=goals,
        world_snapshot=world_snapshot,
        claims=claims,
        moment=moment,
    )
    slot_profiles = _normalize_slot_profiles(
        slot_sources,
        read_at_ns=normalized_read_at_ns,
    )
    receipt = DecisionReceipt(
        moment_id=moment.contract_id,
        mode=ReceiptMode.SHADOW,
        decision_kind=_DECISION_KIND,
        rationale=_RATIONALE,
        selected_goal_id=None,
        input_claim_ids=moment.claim_ids,
        proof_candidate_ids=(),
        proposed_action={},
        metadata=_profile_metadata(
            moment=moment,
            slot_profiles=slot_profiles,
            read_at_ns=normalized_read_at_ns,
        ),
    )
    return adapt_co_f1_profile_receipt(
        receipt,
        envelope=envelope,
        goals=goals,
        world_snapshot=world_snapshot,
        claims=claims,
        moment=moment,
    )


def adapt_co_f1_profile_receipt(
    value: DecisionReceipt | Mapping[str, Any],
    *,
    envelope: CognitiveEnvelope,
    goals: Sequence[GoalIR],
    world_snapshot: WorldSnapshot,
    claims: Sequence[ClaimEnvelope],
    moment: CognitiveMoment,
) -> DecisionReceipt:
    """Strictly reconstruct and validate an F1 receipt and its closed metadata."""

    _validate_moment(
        envelope=envelope,
        goals=goals,
        world_snapshot=world_snapshot,
        claims=claims,
        moment=moment,
    )
    raw_fields = set(value) if isinstance(value, Mapping) else None
    if isinstance(value, DecisionReceipt):
        if type(value) is not DecisionReceipt:
            raise ValueError("typed F1 receipt must be the canonical DecisionReceipt type")
        receipt = adapt_decision_receipt(value.to_dict())
        if set(vars(value)) != set(vars(receipt)):
            raise ValueError("typed F1 receipt must use the exact canonical instance field set")
    else:
        receipt = adapt_decision_receipt(value)
    if raw_fields is not None and raw_fields != set(receipt.to_dict()):
        raise ValueError("serialized F1 receipt must use the exact canonical field set")
    if not receipt.verify_identity():
        raise ValueError("F1 receipt must retain canonical identity")
    if receipt.moment_id != moment.contract_id:
        raise ValueError("F1 receipt is not bound to the supplied moment")
    if receipt.mode is not ReceiptMode.SHADOW:
        raise ValueError("F1 receipt must remain shadow-only")
    if receipt.decision_kind != _DECISION_KIND or receipt.rationale != _RATIONALE:
        raise ValueError("receipt is not an F1 profile receipt")
    if receipt.selected_goal_id is not None or receipt.proof_candidate_ids:
        raise ValueError("F1 profile cannot select a goal or claim proof")
    if receipt.input_claim_ids != moment.claim_ids:
        raise ValueError("F1 receipt claims do not match the supplied moment")
    if receipt.proposed_action:
        raise ValueError("F1 profile cannot propose an action")
    if receipt.authoritative or receipt.action_executed or not receipt.read_only:
        raise ValueError("F1 receipt must be read-only and non-authoritative")
    if set(receipt.metadata) != _PROFILE_METADATA_FIELDS:
        raise ValueError("receipt metadata is not the closed F1 schema")
    if receipt.metadata["co_profile_schema"] != CO_F1_PROFILE_SCHEMA:
        raise ValueError("receipt does not carry the F1 profile schema")
    if receipt.metadata["authority_fence"] != _AUTHORITY_FENCE:
        raise ValueError("receipt authority fence is not canonical")
    if receipt.metadata["reserved_domains"] != _RESERVED_DOMAINS:
        raise ValueError("receipt reserved-domain posture is not canonical")
    if receipt.metadata["observation_join_claimed"] is not False:
        raise ValueError("F1 cannot claim a live observation join")
    if receipt.metadata["profile_scope"] != "contract_profile_only_not_live_join":
        raise ValueError("receipt exceeds the F1 profile scope")
    read_at_ns = _nonnegative_int(receipt.metadata["read_at_ns"], "metadata.read_at_ns")
    profiles = _validate_normalized_profiles(
        receipt.metadata["slot_profiles"],
        read_at_ns=read_at_ns,
    )
    expected = _profile_metadata(
        moment=moment,
        slot_profiles=profiles,
        read_at_ns=read_at_ns,
    )
    if receipt.metadata != expected:
        raise ValueError("F1 receipt metadata is not internally reproducible")
    return receipt


__all__ = [
    "CO_F1_PROFILE_SCHEMA",
    "adapt_co_f1_profile_receipt",
    "build_co_f1_profile",
]
