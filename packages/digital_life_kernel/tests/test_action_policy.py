from __future__ import annotations

from packages.digital_life_kernel.action_policy import propose_actions
from packages.digital_life_kernel.models import LifeSignal


def test_privacy_signal_maps_to_review_proposal():
    proposals = propose_actions([LifeSignal("privacy", "privacy_risk", 0.8, [], "test")])

    assert proposals[0].action_type == "privacy_review"
    assert proposals[0].requires_user_approval is True
    assert proposals[0].mutates_local_brain is False
    assert proposals[0].mutates_production is False


def test_empty_signals_do_nothing_is_still_review_gated():
    proposals = propose_actions([])

    assert proposals[0].action_type == "do_nothing"
    assert proposals[0].safe_by_default is True
