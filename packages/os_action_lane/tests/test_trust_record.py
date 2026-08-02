# -*- coding: utf-8 -*-
"""Trust-tier promotion recommendation — evidence-gated, never self-promoting."""

from __future__ import annotations

import json
import time

from packages.os_action_lane.models import TrustTier
from packages.os_action_lane.trust_record import (
    MIN_ACTIONS, promotion_recommendation)


def _write_audit(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _row(tier=1, executed=True, ok=True, detail="ok", days_ago=5.0):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days_ago * 86400))
    return {"tier": tier, "executed": executed, "ok": ok, "detail": detail, "ts": ts}


def test_not_enough_track_record(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_audit(p, [_row() for _ in range(3)])
    rec = promotion_recommendation(p, TrustTier.ASSIST)
    assert rec["recommend"] is False
    assert f"3/{MIN_ACTIONS}" in rec["reason"]


def test_failure_blocks_recommendation(tmp_path):
    p = tmp_path / "audit.jsonl"
    rows = [_row() for _ in range(MIN_ACTIONS)]
    rows[7] = _row(ok=False)
    _write_audit(p, rows)
    rec = promotion_recommendation(p, TrustTier.ASSIST)
    assert rec["recommend"] is False and "실패" in rec["reason"]


def test_rejection_blocks_recommendation(tmp_path):
    p = tmp_path / "audit.jsonl"
    rows = [_row() for _ in range(MIN_ACTIONS)]
    rows[3] = _row(executed=False, ok=False, detail="human rejected")
    _write_audit(p, rows)
    rec = promotion_recommendation(p, TrustTier.ASSIST)
    assert rec["recommend"] is False and "거절" in rec["reason"]


def test_clean_record_recommends_but_never_promotes(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_audit(p, [_row(days_ago=6.0 - i * 0.2) for i in range(MIN_ACTIONS)])
    rec = promotion_recommendation(p, TrustTier.ASSIST)
    assert rec["recommend"] is True
    assert rec["next_tier"] == int(TrustTier.GUARDED)
    assert "사용자의 손으로" in rec["reason"]  # the grant is always human


def test_top_tier_has_no_next(tmp_path):
    p = tmp_path / "audit.jsonl"
    _write_audit(p, [_row(tier=3) for _ in range(MIN_ACTIONS)])
    rec = promotion_recommendation(p, TrustTier.AUTONOMOUS)
    assert rec["recommend"] is False and rec["next_tier"] is None
