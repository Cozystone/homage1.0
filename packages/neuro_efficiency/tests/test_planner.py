from __future__ import annotations

from neuro_efficiency import build_neuro_efficiency_plan


def test_plan_exposes_efficiency_controls() -> None:
    plan = build_neuro_efficiency_plan(
        {
            "text": "SNN event neuromorphic continual few-shot self-supervised pruning quantization GraphRAG guardrail",
            "module_budget": 4,
            "target_device": "low-power edge cpu",
        }
    )

    assert plan["architecture"] == "ATANOR Neuro-Efficiency Layer"
    assert 0 < plan["event_gate"]["event_density"] <= 1
    assert plan["event_gate"]["sparsity"] > 0
    assert len(plan["module_routing"]["active_modules"]) <= 4
    assert plan["compression"]["quantization_bits"] == 8
    assert plan["energy_estimate"]["reduction_ratio"] > 0.5
    assert plan["learning_plan"]["few_shot"]["prototype_slots"] >= 8


def test_plan_defaults_are_deterministic_shape() -> None:
    plan = build_neuro_efficiency_plan()

    assert plan["workload"]["token_count"] > 0
    assert plan["module_routing"]["modules"]
    assert plan["recommendations"]
    assert plan["research_basis"]
