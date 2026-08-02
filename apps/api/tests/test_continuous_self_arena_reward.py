from __future__ import annotations

from app.routers import continuous_self


def test_raw_arena_scores_cannot_start_self_or_manufacture_dopamine(monkeypatch):
    def forbidden_start():
        raise AssertionError("unverified reward must not start the self loop")

    monkeypatch.setattr(continuous_self, "_ensure_alive", forbidden_start)
    result = continuous_self.selfhood_arena_event(
        {
            "prev_fitness": 0.0,
            "fitness": 1.0,
            "generation": 999,
            "dopamine": 1000,
        }
    )
    assert result == {
        "ok": False,
        "felt": False,
        "reward_signal_accepted": False,
        "reason": "externally_signed_live_bound_evaluation_receipt_required",
        "required_boundary": "packages.autonomy_envelope.evaluation_trust",
    }


def test_forged_receipt_label_does_not_bypass_external_verifier(monkeypatch):
    monkeypatch.setattr(
        continuous_self,
        "_ensure_alive",
        lambda: (_ for _ in ()).throw(
            AssertionError("forged receipt label must not start the self loop")
        ),
    )
    result = continuous_self.selfhood_arena_event(
        {
            "fitness": 1.0,
            "prev_fitness": 0.0,
            "evaluation_receipt": {"verified": True},
        }
    )
    assert result["ok"] is False
    assert result["reward_signal_accepted"] is False
