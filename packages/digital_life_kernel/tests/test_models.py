from __future__ import annotations

import pytest

from packages.digital_life_kernel.models import LifeActionProposal, LifeSignal


def test_life_signal_bounds_severity():
    with pytest.raises(ValueError):
        LifeSignal("s", "knowledge_gap", 1.2, [], "test")


def test_life_action_proposal_safe_by_default():
    proposal = LifeActionProposal(
        "a1",
        "run_quality_audit",
        "Audit",
        "Prepare audit.",
        "low",
    )

    assert proposal.safe_by_default is True
    assert proposal.to_dict()["mutates_production"] is False
