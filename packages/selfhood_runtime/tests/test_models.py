from __future__ import annotations

import pytest

from packages.selfhood_runtime.models import SelfhoodRuntimeInput, SelfhoodRuntimeProposal, SelfhoodRuntimeResult


def test_text_input_requires_text() -> None:
    with pytest.raises(ValueError):
        SelfhoodRuntimeInput("i1", "text")


def test_result_rejects_actual_mutation() -> None:
    proposal = SelfhoodRuntimeProposal("p1", "Title", "Summary", "answer_user")
    with pytest.raises(ValueError):
        SelfhoodRuntimeResult(
            "r1",
            "i1",
            "completed",
            [proposal],
            [],
            {},
            actual_mutations={"production_store_mutated": True},
        )
