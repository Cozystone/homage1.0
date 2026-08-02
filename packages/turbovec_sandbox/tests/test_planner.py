from __future__ import annotations

import pytest

from packages.turbovec_sandbox.planner import HotColdSplitPlan


def test_hot_cold_split_estimates_compression():
    plan = HotColdSplitPlan(hot_vectors=100, cold_vectors=900, dimension=512)

    assert plan.baseline_bytes == 1000 * 512 * 8
    assert plan.planned_bytes == (100 * 512 * 4) + (900 * 512)
    assert plan.compression_ratio > 4.0


def test_plan_cannot_claim_production_mutation():
    with pytest.raises(ValueError):
        HotColdSplitPlan(hot_vectors=1, cold_vectors=1, dimension=2, production_store_mutated=True)
