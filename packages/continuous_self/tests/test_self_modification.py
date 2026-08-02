"""Gated self-modification: propose → sandbox → operator decision → bounded apply.
The invariant that matters most: NOTHING applies without a human 'approved' status."""
from __future__ import annotations

from packages.continuous_self.self_modification import (
    TUNABLE,
    apply_approved,
    decide,
    list_proposals,
    propose_self_tuning,
    sandbox_validate,
)
from packages.continuous_self.self_state import SelfState


def _restless_self() -> SelfState:
    s = SelfState()
    for _ in range(10):
        s.vitals_history.append({"at": 0, "energy": 0.7, "curiosity": 0.75,
                                 "uncertainty": 0.4, "valence": 0.5})
    return s


def test_mind_proposes_from_its_own_history(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    p = propose_self_tuning(_restless_self(), ledger, {"initiative_every": 15})
    assert p is not None and p["status"] == "pending"
    assert p["param"] == "initiative_every" and p["proposed"] < 15  # wants to act MORE
    assert p["safety"]["auto_apply"] is False and p["safety"]["requires_operator"] is True
    assert p["sandbox"]["ok"] is True  # evidence attached


def test_no_proposal_spam_while_one_is_pending(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    s = _restless_self()
    assert propose_self_tuning(s, ledger, {"initiative_every": 15}) is not None
    assert propose_self_tuning(s, ledger, {"initiative_every": 15}) is None
    assert len(list_proposals(ledger)) == 1


def test_nothing_applies_without_operator_approval(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    propose_self_tuning(_restless_self(), ledger, {"initiative_every": 15})
    params = {"initiative_every": 15}
    assert apply_approved(ledger, params) == []          # pending → NOT applied
    assert params["initiative_every"] == 15


def test_operator_approval_applies_within_bounds(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    p = propose_self_tuning(_restless_self(), ledger, {"initiative_every": 15})
    decided = decide(ledger, p["id"], approve=True, operator_note="ok")
    assert decided and decided["status"] == "approved"
    params = {"initiative_every": 15}
    applied = apply_approved(ledger, params)
    assert len(applied) == 1 and params["initiative_every"] == p["proposed"]
    # idempotent: re-apply does nothing
    assert apply_approved(ledger, params) == []


def test_rejection_never_applies(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    p = propose_self_tuning(_restless_self(), ledger, {"initiative_every": 15})
    decide(ledger, p["id"], approve=False, operator_note="no")
    params = {"initiative_every": 15}
    assert apply_approved(ledger, params) == []
    assert params["initiative_every"] == 15


def test_sandbox_rejects_out_of_bounds():
    r = sandbox_validate("initiative_every", 1)  # below hard min
    assert r["ok"] is False
    r2 = sandbox_validate("ease_rate", 0.3)
    assert r2["ok"] is True and r2["simulated_ticks"] > 0
    assert "실제 자아는 건드리지" in r2["note"]


def test_tunable_whitelist_is_small_and_bounded():
    for spec in TUNABLE.values():
        assert spec["min"] < spec["max"]
    assert set(TUNABLE) == {"initiative_every", "reflect_every", "ease_rate"}
