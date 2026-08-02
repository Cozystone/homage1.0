# -*- coding: utf-8 -*-
"""Trust policy — the Codex/Claude approval model over (risk × tier).

The trust tier is the ONE dial the user turns to trade safety for autonomy:

 OBSERVE — nothing runs; the lane narrates the plan it WOULD execute.
 ASSIST — every action holds for an explicit yes (voice '' / click). Nothing
 touches the machine without a per-action human confirmation.
 GUARDED — reversible things (open app, focus, type, volume) run immediately;
 anything that can lose data holds for approval.
 AUTONOMOUS — the user accepted the risk: destructive actions run without asking.
 CATASTROPHIC (whole-disk / irreversible) STILL confirms once — even
 full autonomy keeps a floor, exactly as coding agents do; the floor is
 explicit and documented, not a hidden veto.

The tier is trust EARNED and GRANTED, not assumed: it starts at ASSIST and the user
raises it deliberately.
"""
from __future__ import annotations

from .models import GateOutcome, RiskLevel, TrustTier


def gate(risk: RiskLevel, tier: TrustTier) -> GateOutcome:
    if tier == TrustTier.OBSERVE:
        return GateOutcome.NEEDS_APPROVAL  # OBSERVE never executes; the lane dry-runs
    if tier == TrustTier.ASSIST:
        return GateOutcome.NEEDS_APPROVAL  # every action confirmed
    if tier == TrustTier.GUARDED:
        return (GateOutcome.EXECUTE if risk <= RiskLevel.REVERSIBLE
                else GateOutcome.NEEDS_APPROVAL)
    # AUTONOMOUS
    if risk >= RiskLevel.CATASTROPHIC:
        return GateOutcome.NEEDS_APPROVAL  # the accepted-risk floor
    return GateOutcome.EXECUTE


# human-readable rationale for the certificate/voice reply
def rationale(risk: RiskLevel, tier: TrustTier, outcome: GateOutcome) -> str:
    if outcome == GateOutcome.EXECUTE:
        return {
            RiskLevel.READONLY: "읽기 전용이라 바로 실행합니다.",
            RiskLevel.REVERSIBLE: "되돌릴 수 있는 작업이라 바로 실행합니다.",
            RiskLevel.DESTRUCTIVE: "자율 모드에서 승인된 위험이라 실행합니다.",
        }.get(risk, "실행합니다.")
    if tier == TrustTier.OBSERVE:
        return "관찰 모드라 실행하지 않고 계획만 보여드립니다."
    if risk >= RiskLevel.CATASTROPHIC:
        return "되돌릴 수 없는 전체 시스템 작업입니다. 자율 모드라도 한 번 확인이 필요합니다."
    return "승인이 필요한 작업입니다. 실행할까요?"
