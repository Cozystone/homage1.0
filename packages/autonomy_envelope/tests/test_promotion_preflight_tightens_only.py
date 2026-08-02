# -*- coding: utf-8 -*-
"""M0c — the four checks ride with a queued promotion, and they may only ever TIGHTEN it.

    pytest packages/autonomy_envelope/tests/test_promotion_preflight_tightens_only.py

`packages.self_check` earned its authority on 2026-07-29 -- five confident-and-wrong results refused,
two real ones still allowed -- and then had zero consumers for a day while every experiment script
hand-rolled its own pass condition, four of which passed vacuously. This wires it into the one place in
the live system where a measurement is offered up for belief.

WHAT THESE TESTS ARE REALLY DEFENDING is the direction of the change. `operator-signed, default-deny` is
a standing constraint, and a check bolted onto a promotion path is exactly the kind of addition that
quietly becomes an approval mechanism later. So the property under test is not "preflight runs" but
"preflight cannot grant" -- no entry, whatever its evidence, comes out of the queue in a state that needs
less from the operator than before.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from packages.autonomy_envelope.audit_ledger import AuditLedger
from packages.autonomy_envelope.promotion_queue import NightlyPromotionQueue

WEAK = {"observed_source": "ALE", "intended_source": "ALE", "base_rate": 0.5, "n": 10,
        "real_score": 0.5, "control_score": 0.5, "target_size": 0.904, "unit_size": 0.75}
STRONG = {"observed_source": "CARLA", "intended_source": "CARLA", "base_rate": 0.42, "n": 400,
          "real_score": 0.81, "control_score": 0.53, "target_size": 18.0, "unit_size": 4.0}


@pytest.fixture
def q(tmp_path: Path):
    return NightlyPromotionQueue(staging_dir=tmp_path, ledger=AuditLedger(tmp_path / "ledger.jsonl"))


def test_every_queued_entry_still_requires_the_operator(q):
    """The load-bearing one. Preflight may add a reason to refuse and may never remove one."""
    recs = [q.queue({"item_id": "a", "title": "no evidence"}),
            q.queue({"item_id": "b", "title": "weak", "evidence": WEAK}),
            q.queue({"item_id": "c", "title": "strong", "evidence": STRONG})]
    for r in recs:
        assert r["status"].startswith("pending_operator_signature"), (
            f"{r['item_id']} came out of the queue as {r['status']!r}. Preflight is a tightening only; "
            f"nothing here may produce a state that asks LESS of the operator."
        )
        assert r["production_store_mutated"] is False


def test_weak_evidence_is_flagged_so_it_cannot_be_approved_unseen(q):
    r = q.queue({"item_id": "b", "title": "ten samples where thirty are needed", "evidence": WEAK})
    assert r["status"] == "pending_operator_signature_preflight_failed"
    assert r["preflight"]["may_promote"] is False
    assert any("30" in b for b in r["preflight"]["blocked_by"]), r["preflight"]["blocked_by"]


def test_strong_evidence_is_not_flagged(q):
    """A gate that refuses everything is not a gate. self_check's retro pass turns on this too."""
    r = q.queue({"item_id": "c", "title": "a result that holds", "evidence": STRONG})
    assert r["status"] == "pending_operator_signature"
    assert r["preflight"]["may_promote"] is True


def test_an_entry_with_no_evidence_is_not_punished_for_it(q):
    """A queue is not the place to demand measurements a producer may legitimately not have."""
    r = q.queue({"item_id": "a", "title": "no measurements at all"})
    assert r["status"] == "pending_operator_signature"
    assert "preflight" not in r


def test_the_queue_survives_a_broken_preflight(monkeypatch, q):
    """Losing the extra check degrades the packet; losing the queue would lose review entirely."""
    monkeypatch.setattr(NightlyPromotionQueue, "_preflight_of",
                        lambda self, entry: {"may_promote": False, "claim": "preflight unavailable",
                                             "blocked_by": ["preflight raised: boom"], "checks": []})
    r = q.queue({"item_id": "d", "title": "organ down", "evidence": STRONG})
    assert r["status"] == "pending_operator_signature_preflight_failed"
    assert r["preflight"]["blocked_by"] == ["preflight raised: boom"]
