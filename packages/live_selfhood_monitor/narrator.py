from __future__ import annotations

from .models import LifeSignsSnapshot


def narrate_snapshot(snapshot: LifeSignsSnapshot, style: str = "concise_ko") -> str:
    """Narrate a life-sign snapshot without claiming real consciousness or AGI."""

    if style != "concise_ko":
        return _narrate_en(snapshot)
    safety = "실제 기억 저장, production 변경, 후보 승격, real P2P, 생성 코드 실행, 상시 청취는 모두 잠겨 있습니다."
    if snapshot.alive_status == "alive":
        action = snapshot.latest_action.get("title") if snapshot.latest_action else "아직 제안된 행동은 없습니다"
        wake = snapshot.latest_wake_reason or "최근 tick"
        approval = f" 승인 대기 {len(snapshot.pending_approvals)}건이 있습니다." if snapshot.pending_approvals else " 승인 대기는 없습니다."
        return f"ATANOR는 기능적 heartbeat 기준으로 살아 있는 상태로 보입니다. {wake} 때문에 깨어났고, 최근에는 {action}을 준비했습니다.{approval} {safety}"
    if snapshot.alive_status == "resting":
        reason = snapshot.latest_wake_reason or "리듬 정책"
        return f"ATANOR는 현재 쉬는 상태입니다. 이유는 {reason}이며, 다음 관찰까지 대기합니다. {safety}"
    if snapshot.alive_status == "stalled":
        return f"최근 heartbeat가 오래되어 life cycle이 멈췄거나 대기 중일 수 있습니다. stop marker와 scheduler 상태를 확인해야 합니다. {safety}"
    if snapshot.alive_status == "stopped":
        return f"ATANOR life signs monitor는 중지 상태입니다. 감시 세션은 bounded이며 다시 켜려면 명시적 opt-in이 필요합니다. {safety}"
    if snapshot.pending_approvals:
        return f"ATANOR는 사용자 승인을 기다리고 있습니다. 승인 대기 {len(snapshot.pending_approvals)}건이 있으며 적용은 수행하지 않습니다. {safety}"
    return f"ATANOR의 life signs 상태는 아직 불명확합니다. 관찰 데이터나 heartbeat가 더 필요합니다. {safety}"


def _narrate_en(snapshot: LifeSignsSnapshot) -> str:
    safety = "Local Brain writes, production mutation, promotion, real P2P, generated code, and always-listening voice remain locked."
    if snapshot.alive_status == "alive":
        return f"ATANOR appears functionally alive by heartbeat and tick evidence. Pending approvals: {len(snapshot.pending_approvals)}. {safety}"
    if snapshot.alive_status == "resting":
        return f"ATANOR is resting under its rhythm policy. {safety}"
    if snapshot.alive_status == "stalled":
        return f"ATANOR may be stalled because the latest heartbeat is stale. Check the stop marker and scheduler state. {safety}"
    if snapshot.alive_status == "stopped":
        return f"ATANOR life signs monitoring is stopped and requires explicit opt-in to run again. {safety}"
    return f"ATANOR life signs are unknown or idle. {safety}"
