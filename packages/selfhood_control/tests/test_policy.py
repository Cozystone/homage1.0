from __future__ import annotations

from dataclasses import replace

from packages.selfhood_control.models import SelfhoodDecision
from packages.selfhood_control.policy import SelfhoodSafetyPolicy, validate_decision


def test_policy_allows_safe_decision() -> None:
    result = validate_decision(SelfhoodDecision("d", "i", [], action="ask_user"), SelfhoodSafetyPolicy())
    assert result.allowed is True


def test_policy_blocks_voice_memory_write() -> None:
    decision = SelfhoodDecision("d", "i", [], voice_response={"writes_local_brain": True})
    result = validate_decision(decision, SelfhoodSafetyPolicy())
    assert result.allowed is False
    assert result.reason == "voice_memory_write_blocked"


def test_policy_requires_user_approval() -> None:
    decision = replace(SelfhoodDecision("d", "i", []), requires_user_approval=False)
    result = validate_decision(decision, SelfhoodSafetyPolicy())
    assert result.allowed is False
    assert result.reason == "user_approval_required"
