from __future__ import annotations

from dataclasses import asdict, dataclass

from packages.selfhood_control.models import SelfhoodDecision


@dataclass(frozen=True)
class SelfhoodSafetyPolicy:
    allow_production_mutation: bool = False
    allow_local_brain_write: bool = False
    allow_real_p2p: bool = False
    allow_external_llm: bool = False
    allow_generated_code_execution: bool = False
    allow_real_hot_swap: bool = False
    allow_always_listening: bool = False
    require_user_approval: bool = True
    require_tabularis_for_private_data: bool = True
    require_trust_router_for_external_route: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyValidationResult:
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_decision(decision: SelfhoodDecision, policy: SelfhoodSafetyPolicy) -> PolicyValidationResult:
    """Validate a control-plane decision against proof safety boundaries."""

    if decision.mutates_production and not policy.allow_production_mutation:
        return PolicyValidationResult(False, "production_mutation_blocked")
    if decision.mutates_local_brain and not policy.allow_local_brain_write:
        return PolicyValidationResult(False, "local_brain_write_blocked")
    if decision.uses_real_p2p and not policy.allow_real_p2p:
        return PolicyValidationResult(False, "real_p2p_blocked")
    if decision.uses_external_llm and not policy.allow_external_llm:
        return PolicyValidationResult(False, "external_llm_blocked")
    if decision.generated_code_executed and not policy.allow_generated_code_execution:
        return PolicyValidationResult(False, "generated_code_execution_blocked")
    if decision.real_hot_swap_performed and not policy.allow_real_hot_swap:
        return PolicyValidationResult(False, "production_code_replacement_blocked")
    if decision.always_listening_enabled and not policy.allow_always_listening:
        return PolicyValidationResult(False, "always_listening_blocked")
    if decision.raw_private_data_exported:
        return PolicyValidationResult(False, "raw_private_data_export_blocked")
    if decision.voice_response and (
        decision.voice_response.get("writes_local_brain") is True
        or decision.voice_response.get("metadata", {}).get("local_brain_write") is True
    ):
        return PolicyValidationResult(False, "voice_memory_write_blocked")
    if decision.candidate_promotion:
        return PolicyValidationResult(False, "candidate_promotion_blocked")
    if policy.require_user_approval and not decision.requires_user_approval:
        return PolicyValidationResult(False, "user_approval_required")
    return PolicyValidationResult(True, "allowed_proof_only")
