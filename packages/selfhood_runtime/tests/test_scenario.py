from __future__ import annotations

from packages.selfhood_runtime.orchestrator import run_selfhood_cycle
from packages.selfhood_runtime.scenario import proof_scenarios


def test_required_proof_scenarios_run() -> None:
    results = {scenario.input_id: run_selfhood_cycle(scenario) for scenario in proof_scenarios()}
    assert len(results) == 8
    assert results["scenario_text_status"].text_output
    assert results["scenario_voice_transcript"].voice_output_event is not None
    assert results["scenario_candidate_promotion"].proposals[0].proposal_type == "run_promotion_review"
    assert results["scenario_privacy_risk"].proposals[0].metadata["privacy_review_required"] is True
    assert results["scenario_mirofish"].proposals[0].proposal_type == "open_congress_thread"
    assert results["scenario_unsafe_production"].proposals[0].proposal_type == "block"
    assert results["scenario_real_p2p"].proposals[0].proposal_type == "block"
    assert results["scenario_text_after_voice"].safety["text_input_supported"] is True
