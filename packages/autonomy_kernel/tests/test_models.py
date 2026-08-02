from __future__ import annotations

import pytest

from packages.autonomy_kernel.event_stream import utc_now
from packages.autonomy_kernel.models import AutonomyProposal, DeficitSignal, SelfModelSnapshot, WorldModelSnapshot


def test_model_validation() -> None:
    world = WorldModelSnapshot("w", 1, 2, 3, [], [], [], utc_now())
    assert world.concepts == 1
    self_model = SelfModelSnapshot("s", 0, [], [], {}, [], [], utc_now())
    assert self_model.local_memory_count == 0
    with pytest.raises(ValueError):
        DeficitSignal("d", "knowledge_gap", 2.0, 0.1, "test", [])


def test_proposal_defaults_are_safe() -> None:
    proposal = AutonomyProposal("p", "research_question", "Title", "Summary", "Rationale")
    assert proposal.required_approval is True
    assert proposal.generated_code_executed is False
    assert proposal.mutates_production is False
    assert proposal.mutates_local_brain is False

