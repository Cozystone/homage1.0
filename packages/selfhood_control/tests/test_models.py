from __future__ import annotations

import pytest

from packages.selfhood_control.models import SelfhoodContext, SelfhoodDecision, SelfhoodInput


def test_model_validation() -> None:
    with pytest.raises(ValueError):
        SelfhoodInput("", "proof_fixture")
    with pytest.raises(ValueError):
        SelfhoodInput("i", "voice_transcript")
    context = SelfhoodContext("c", {}, {}, {}, [], None, {}, "now")
    assert context.context_id == "c"


def test_decision_rejects_mutations() -> None:
    with pytest.raises(ValueError):
        SelfhoodDecision("d", "i", [], mutates_production=True)
    with pytest.raises(ValueError):
        SelfhoodDecision("d", "i", [], mutates_local_brain=True)
    with pytest.raises(ValueError):
        SelfhoodDecision("d", "i", [], uses_real_p2p=True)
    with pytest.raises(ValueError):
        SelfhoodDecision("d", "i", [], generated_code_executed=True)
