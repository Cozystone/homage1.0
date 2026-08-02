from __future__ import annotations

import pytest

from packages.airllm_offload_sandbox.planner import HardwareProfile, ModelProfile, OffloadPlan, plan_offload


def test_too_large_model_blocked_by_disk():
    plan = plan_offload(
        ModelProfile("huge", parameter_billion=70.0, quantization_bits=4, layer_count=80),
        HardwareProfile(ram_gib=16.0, vram_gib=4.0, disk_free_gib=8.0),
    )

    assert plan.status == "blocked"
    assert plan.reason == "insufficient_disk_budget"


def test_advisory_plan_for_medium_model():
    plan = plan_offload(
        ModelProfile("medium", parameter_billion=7.0, quantization_bits=4, layer_count=32),
        HardwareProfile(ram_gib=32.0, vram_gib=8.0, disk_free_gib=80.0),
    )

    assert plan.status == "advisory_ok"
    assert plan.advisory_only is True
    assert plan.model_downloaded is False
    assert plan.production_answer_path_integrated is False
    assert plan.gpu_layers > 0


def test_plan_cannot_claim_runtime_side_effects():
    with pytest.raises(ValueError):
        OffloadPlan("advisory_ok", "bad", 1, 1, 1.0, model_downloaded=True)
