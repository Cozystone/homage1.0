"""Structural adapters into the canonical cognitive contracts.

The adapters depend only on mappings, ``to_dict`` objects, and this package.  They
do not import organ APIs, start services, perform I/O, or confer action authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, TypeVar

from packages.cognitive_core.canonical import SCHEMA_VERSION
from packages.cognitive_core.contracts import (
    ClaimEnvelope,
    CognitiveEnvelope,
    CognitiveMoment,
    DecisionReceipt,
    EpistemicTier,
    GoalIR,
    GoalOrigin,
    ProofCandidate,
    ReceiptMode,
    WorldSnapshot,
)
from packages.cognitive_core.cycle import (
    CanonicalEntityRef,
    CycleEvent,
    CycleReceipt,
    RequestCycle,
)


ContractT = TypeVar(
    "ContractT",
    CognitiveEnvelope,
    GoalIR,
    ClaimEnvelope,
    ProofCandidate,
    WorldSnapshot,
    CognitiveMoment,
    DecisionReceipt,
)


_TIER_ALIASES = {
    "perceived": EpistemicTier.OBSERVED,
    "observation": EpistemicTier.OBSERVED,
    "observed": EpistemicTier.OBSERVED,
    "record": EpistemicTier.RECORDED,
    "recorded": EpistemicTier.RECORDED,
    "inference": EpistemicTier.INFERRED,
    "inferred": EpistemicTier.INFERRED,
    "projection": EpistemicTier.PREDICTED,
    "projected": EpistemicTier.PREDICTED,
    "predicted": EpistemicTier.PREDICTED,
    "retrodiction": EpistemicTier.RETRODICTED,
    "retrodicted": EpistemicTier.RETRODICTED,
    "unknown": EpistemicTier.UNKNOWN,
}

_ORIGIN_ALIASES = {
    "user": GoalOrigin.EXPLICIT_USER,
    "explicit": GoalOrigin.EXPLICIT_USER,
    "explicit_user": GoalOrigin.EXPLICIT_USER,
    "delegated": GoalOrigin.DELEGATED_USER,
    "delegated_user": GoalOrigin.DELEGATED_USER,
    "system": GoalOrigin.SYSTEM_MAINTENANCE,
    "system_maintenance": GoalOrigin.SYSTEM_MAINTENANCE,
    "intrinsic": GoalOrigin.INTRINSIC,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    raise TypeError("adapter input must be a mapping or expose to_dict() -> mapping")


def _value(payload: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return default


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise ValueError(f"adapter input requires {name}")
    return value


def _coalesced_enum(
    payload: Mapping[str, Any],
    names: tuple[str, ...],
    normalize: Callable[[Any], Any],
    label: str,
) -> Any:
    present = [(name, payload[name]) for name in names if name in payload]
    if not present:
        raise ValueError(f"adapter input requires {label}")
    normalized = [(name, normalize(value)) for name, value in present]
    if any(value != normalized[0][1] for _, value in normalized[1:]):
        raise ValueError(f"conflicting {label} adapter fields")
    return normalized[0][1]


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    return tuple(value)


def _check_schema(payload: Mapping[str, Any]) -> None:
    claimed = payload.get("schema_version")
    if claimed is not None and claimed != SCHEMA_VERSION:
        raise ValueError(f"unsupported cognitive contract schema: {claimed!r}")


def _reject_truthy(payload: Mapping[str, Any], names: tuple[str, ...], reason: str) -> None:
    claimed = [
        name
        for name in names
        if name in payload and payload[name] is not None and payload[name] is not False
    ]
    if claimed:
        raise ValueError(f"{reason}: {', '.join(sorted(claimed))}")


def _require_fixed_bool(payload: Mapping[str, Any], name: str, expected: bool) -> None:
    if name in payload and payload[name] is not expected:
        raise ValueError(f"{name} must remain the literal value {expected!r}")


def _finish(contract: ContractT, payload: Mapping[str, Any]) -> ContractT:
    claimed_type = payload.get("contract_type")
    if claimed_type is not None and claimed_type != type(contract).__name__:
        raise ValueError("contract_type does not match adapted contract")
    claimed_id = payload.get("contract_id")
    if claimed_id is not None and claimed_id != contract.contract_id:
        raise ValueError("claimed contract_id does not match canonical content")
    claimed_hash = payload.get("content_hash")
    if claimed_hash is not None and claimed_hash != contract.content_hash:
        raise ValueError("claimed content_hash does not match canonical content")
    return contract


def _tier(value: Any) -> EpistemicTier:
    if isinstance(value, EpistemicTier):
        return value
    normalized = str(value).strip().lower()
    try:
        return _TIER_ALIASES[normalized]
    except KeyError as error:
        raise ValueError(f"unknown epistemic tier: {value!r}") from error


def _origin(value: Any) -> GoalOrigin:
    if isinstance(value, GoalOrigin):
        return value
    normalized = str(value).strip().lower()
    try:
        return _ORIGIN_ALIASES[normalized]
    except KeyError as error:
        raise ValueError(f"unknown goal origin: {value!r}") from error


def adapt_cognitive_envelope(value: Any) -> CognitiveEnvelope:
    payload = _mapping(value)
    _check_schema(payload)
    _require_fixed_bool(payload, "cognition_only", True)
    _require_fixed_bool(payload, "read_only", True)
    _reject_truthy(
        payload,
        (
            "autonomy_authority",
            "truth_mutation_allowed",
            "safety_mutation_allowed",
            "permission_mutation_allowed",
            "intrinsic_override_allowed",
        ),
        "a cognitive envelope cannot claim action or policy authority",
    )
    contract = CognitiveEnvelope(
        session_id=_require(_value(payload, "session_id", "session"), "session_id"),
        explicit_user_goal_ids=_sequence(
            _value(payload, "explicit_user_goal_ids", "user_goal_ids", default=())
        ),
        intrinsic_goal_ids=_sequence(payload.get("intrinsic_goal_ids", ())),
        world_snapshot_id=_value(payload, "world_snapshot_id", "snapshot_id"),
        hormone_signals=_value(payload, "hormone_signals", "hormones", default={}),
        resource_limits=_value(payload, "resource_limits", "resources", default={}),
        context=payload.get("context", {}),
    )
    return _finish(contract, payload)


def adapt_goal_ir(value: Any) -> GoalIR:
    payload = _mapping(value)
    _check_schema(payload)
    _reject_truthy(
        payload,
        ("can_authorize_actions", "can_override_safety"),
        "a goal contract cannot claim action or safety authority",
    )
    origin = _coalesced_enum(payload, ("origin", "source"), _origin, "origin")
    if origin is GoalOrigin.INTRINSIC:
        _reject_truthy(
            payload,
            (
                "override_explicit_user",
                "intrinsic_override_allowed",
                "supersedes_user_goal",
            ),
            "an intrinsic goal cannot override an explicit user goal",
        )
    contract = GoalIR(
        statement=_require(_value(payload, "statement", "goal", "text"), "statement"),
        origin=origin,
        priority=payload.get("priority", 50),
        parent_goal_ids=_sequence(payload.get("parent_goal_ids", ())),
        constraints=_sequence(payload.get("constraints", ())),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_claim_envelope(value: Any) -> ClaimEnvelope:
    payload = _mapping(value)
    _check_schema(payload)
    tier = _coalesced_enum(
        payload,
        ("tier", "epistemic_tier", "status"),
        _tier,
        "tier",
    )
    observed_flags = [
        payload[name]
        for name in ("is_observed", "observed", "fact")
        if name in payload
    ]
    if any(flag is not True and flag is not False for flag in observed_flags):
        raise ValueError("observed/fact adapter flags must be literal booleans")
    if observed_flags and any(flag is not observed_flags[0] for flag in observed_flags[1:]):
        raise ValueError("conflicting observed/fact adapter flags")
    observed_claim = observed_flags[0] if observed_flags else None
    if observed_claim is True and tier not in {
        EpistemicTier.OBSERVED,
        EpistemicTier.RECORDED,
    }:
        raise ValueError("a non-observed tier cannot be adapted as an observed fact")
    if "accepted_as_observed_fact" in payload:
        accepted = payload["accepted_as_observed_fact"]
        if accepted is not True and accepted is not False:
            raise ValueError("accepted_as_observed_fact must be a literal boolean")
        expected = tier in {EpistemicTier.OBSERVED, EpistemicTier.RECORDED}
        if accepted is not expected:
            raise ValueError(
                "accepted_as_observed_fact cannot contradict the epistemic tier"
            )
    contract = ClaimEnvelope(
        statement=_require(_value(payload, "statement", "claim", "text"), "statement"),
        tier=tier,
        confidence=payload.get("confidence"),
        source_refs=_sequence(_value(payload, "source_refs", "provenance", default=())),
        source_claim_ids=_sequence(payload.get("source_claim_ids", ())),
        lineage_tiers=tuple(
            _tier(item) for item in _sequence(payload.get("lineage_tiers", ()))
        ),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_proof_candidate(value: Any) -> ProofCandidate:
    payload = _mapping(value)
    _check_schema(payload)
    _reject_truthy(
        payload,
        ("accepted", "accepted_as_proof", "truth_mutation_allowed"),
        "a ProofCandidate cannot claim accepted-proof status",
    )
    contract = ProofCandidate(
        claim_id=_require(payload.get("claim_id"), "claim_id"),
        method=_require(payload.get("method"), "method"),
        premise_claim_ids=_sequence(payload.get("premise_claim_ids", ())),
        derivation_steps=_sequence(_value(payload, "derivation_steps", "steps", default=())),
        verifier_refs=_sequence(payload.get("verifier_refs", ())),
        confidence=payload.get("confidence"),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_world_snapshot(value: Any) -> WorldSnapshot:
    payload = _mapping(value)
    _check_schema(payload)
    _require_fixed_bool(payload, "read_only", True)
    _reject_truthy(
        payload,
        ("writable", "truth_mutation_allowed"),
        "a WorldSnapshot is read-only",
    )
    contract = WorldSnapshot(
        world_time=_require(_value(payload, "world_time", "time"), "world_time"),
        snapshot_index=_require(
            _value(payload, "snapshot_index", "index"),
            "snapshot_index",
        ),
        observed_claim_ids=_sequence(payload.get("observed_claim_ids", ())),
        recorded_claim_ids=_sequence(payload.get("recorded_claim_ids", ())),
        inferred_claim_ids=_sequence(payload.get("inferred_claim_ids", ())),
        predicted_claim_ids=_sequence(
            _value(payload, "predicted_claim_ids", "projected_claim_ids", default=())
        ),
        retrodicted_claim_ids=_sequence(payload.get("retrodicted_claim_ids", ())),
        parent_snapshot_id=payload.get("parent_snapshot_id"),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_cognitive_moment(value: Any) -> CognitiveMoment:
    payload = _mapping(value)
    _check_schema(payload)
    _reject_truthy(
        payload,
        (
            "truth_mutation_allowed",
            "safety_mutation_allowed",
            "permission_mutation_allowed",
            "action_authority",
        ),
        "a CognitiveMoment cannot claim action or policy authority",
    )
    contract = CognitiveMoment(
        moment_index=_require(_value(payload, "moment_index", "index"), "moment_index"),
        envelope_id=_require(payload.get("envelope_id"), "envelope_id"),
        world_snapshot_id=_require(payload.get("world_snapshot_id"), "world_snapshot_id"),
        active_goal_ids=_sequence(payload.get("active_goal_ids", ())),
        selected_goal_id=payload.get("selected_goal_id"),
        claim_ids=_sequence(payload.get("claim_ids", ())),
        proof_candidate_ids=_sequence(payload.get("proof_candidate_ids", ())),
        attention_targets=_sequence(payload.get("attention_targets", ())),
        hormone_signals=_value(payload, "hormone_signals", "hormones", default={}),
        resource_state=_value(payload, "resource_state", "resources", default={}),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_decision_receipt(value: Any) -> DecisionReceipt:
    payload = _mapping(value)
    _check_schema(payload)
    _require_fixed_bool(payload, "read_only", True)
    _reject_truthy(
        payload,
        ("authoritative", "action_executed", "authorized", "allowed"),
        "an M1 DecisionReceipt cannot authorize or execute an action",
    )
    mode = ReceiptMode(_require(payload.get("mode"), "mode"))
    if "shadow" in payload and payload["shadow"] is not (mode is ReceiptMode.SHADOW):
        raise ValueError("shadow flag must be derived from receipt mode")
    contract = DecisionReceipt(
        moment_id=_require(payload.get("moment_id"), "moment_id"),
        mode=mode,
        decision_kind=_require(payload.get("decision_kind"), "decision_kind"),
        rationale=_require(payload.get("rationale"), "rationale"),
        selected_goal_id=payload.get("selected_goal_id"),
        input_claim_ids=_sequence(payload.get("input_claim_ids", ())),
        proof_candidate_ids=_sequence(payload.get("proof_candidate_ids", ())),
        proposed_action=payload.get("proposed_action", {}),
        metadata=payload.get("metadata", {}),
    )
    return _finish(contract, payload)


def adapt_canonical_entity_ref(value: Any) -> CanonicalEntityRef:
    payload = _mapping(value)
    _check_schema(payload)
    return CanonicalEntityRef.from_dict(payload)


def adapt_request_cycle(value: Any) -> RequestCycle:
    payload = _mapping(value)
    _check_schema(payload)
    return RequestCycle.from_dict(payload)


def adapt_cycle_event(value: Any) -> CycleEvent:
    payload = _mapping(value)
    _check_schema(payload)
    return CycleEvent.from_dict(payload)


def adapt_cycle_receipt(value: Any) -> CycleReceipt:
    payload = _mapping(value)
    _check_schema(payload)
    return CycleReceipt.from_dict(payload)


_ADAPTERS: dict[str, Callable[[Any], Any]] = {
    "CognitiveEnvelope": adapt_cognitive_envelope,
    "GoalIR": adapt_goal_ir,
    "ClaimEnvelope": adapt_claim_envelope,
    "ProofCandidate": adapt_proof_candidate,
    "WorldSnapshot": adapt_world_snapshot,
    "CognitiveMoment": adapt_cognitive_moment,
    "DecisionReceipt": adapt_decision_receipt,
    "CanonicalEntityRef": adapt_canonical_entity_ref,
    "RequestCycle": adapt_request_cycle,
    "CycleEvent": adapt_cycle_event,
    "CycleReceipt": adapt_cycle_receipt,
}


def adapt_contract(value: Any) -> Any:
    """Dispatch a serialized contract by its explicit ``contract_type`` field."""

    payload = _mapping(value)
    contract_type = _require(payload.get("contract_type"), "contract_type")
    try:
        adapter = _ADAPTERS[str(contract_type)]
    except KeyError as error:
        raise ValueError(f"unsupported contract_type: {contract_type!r}") from error
    return adapter(payload)
