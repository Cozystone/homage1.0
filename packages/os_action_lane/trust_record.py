# -*- coding: utf-8 -*-
"""Trust-tier promotion RECOMMENDATION from the audit track record (Phase 5).

The Codex model: trust is EARNED and GRANTED, never assumed — so the machine
never promotes itself. What it CAN do is show the evidence: how many actions at
the current tier were approved and succeeded, how many failed, over how long.
When the record clears the bar, the lane RECOMMENDS the next tier; the human
turns the dial (set_tier), and that grant is itself audited.

Criteria (v0, explicit):
  * >= MIN_ACTIONS audited actions at the current tier
  * zero failed executions among them
  * zero rejections in the last MIN_ACTIONS (a rejection = trust withheld)
  * track record spans >= MIN_DAYS days
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .models import TrustTier

MIN_ACTIONS = 20
MIN_DAYS = 3.0

_NEXT = {TrustTier.OBSERVE: TrustTier.ASSIST,
         TrustTier.ASSIST: TrustTier.GUARDED,
         TrustTier.GUARDED: TrustTier.AUTONOMOUS}


def _read_audit(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path or not Path(audit_path).exists():
        return []
    rows = []
    for line in Path(audit_path).read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def promotion_recommendation(audit_path: str | Path, current_tier: TrustTier) -> dict[str, Any]:
    """Evidence-backed recommendation. NEVER changes the tier — it reports."""
    tier = TrustTier(current_tier)
    nxt = _NEXT.get(tier)
    base = {"current_tier": int(tier), "next_tier": int(nxt) if nxt else None,
            "recommend": False}
    if nxt is None:
        return {**base, "reason": "이미 최고 티어입니다. 승격 대상이 없습니다."}

    rows = [r for r in _read_audit(Path(audit_path)) if int(r.get("tier", -1)) == int(tier)]
    executed = [r for r in rows if r.get("executed")]
    failures = [r for r in executed if not r.get("ok")]
    rejections = [r for r in rows if "rejected" in str(r.get("detail", "")).lower()]
    stats = {
        "actions_at_tier": len(rows),
        "executed_ok": len(executed) - len(failures),
        "failures": len(failures),
        "rejections": len(rejections),
    }
    if len(rows) < MIN_ACTIONS:
        return {**base, **stats,
                "reason": f"실적 {len(rows)}/{MIN_ACTIONS}건 — 더 쌓여야 추천할 수 있습니다."}
    if failures:
        return {**base, **stats,
                "reason": f"실패 {len(failures)}건이 기록에 있습니다. 무실패 실적이 기준입니다."}
    if rejections:
        return {**base, **stats,
                "reason": f"최근 거절 {len(rejections)}건 — 사용자가 신뢰를 보류한 흔적입니다."}
    try:
        t0 = time.mktime(time.strptime(str(rows[0].get("ts")), "%Y-%m-%dT%H:%M:%S"))
        span_days = (time.time() - t0) / 86400.0
    except Exception:
        span_days = 0.0
    if span_days < MIN_DAYS:
        return {**base, **stats,
                "reason": f"실적 기간 {span_days:.1f}일/{MIN_DAYS:.0f}일 — 시간이 더 필요합니다."}
    return {
        **base, **stats, "recommend": True, "span_days": round(span_days, 1),
        "reason": (f"{len(rows)}건 무실패·무거절 실적({span_days:.1f}일)이 쌓였습니다. "
                   f"다음 티어로 올릴지 결정해 주세요 — 승격은 언제나 사용자의 손으로."),
    }
