from __future__ import annotations

from packages.spark_chamber.chamber import SparkChamber
from packages.spark_chamber.models import ChaosBudget, SparkInput


def test_chamber_returns_candidate_only_insights_and_safe_invariants() -> None:
    spark = SparkInput(
        "s",
        "proof_fixture",
        {"phase": 0.5, "relations": ["a", "b"], "priorities": [1, 2], "optional_fields": ["x"], "contradictions": [{"claim": "A", "negates": "A"}]},
        deterministic_seed=9,
    )
    report = SparkChamber().run(spark, ChaosBudget(0.2, 2, max_risk_score=0.25))
    assert report.passed is True
    assert report.total_mutations > 0
    assert report.invariants["production_store_mutated"] is False
    assert report.invariants["local_brain_write"] is False
    assert all(insight.candidate_only and insight.requires_review for insight in report.insights)
