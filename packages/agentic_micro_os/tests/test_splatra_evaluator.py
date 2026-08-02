from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.splatra_evaluator import SplatraCosmosEvaluator, SplatraEvaluationRequest


def test_splatra_evaluator_scores_candidate_without_applying_patch() -> None:
    kernel = CapabilityKernel()
    evaluator = SplatraCosmosEvaluator(kernel=kernel)
    token = kernel.issue("splatra_cosmos_evaluate")

    result = evaluator.evaluate(
        SplatraEvaluationRequest(candidate_id="orb_candidate", particle_budget=50_000, target_fps=60),
        token,
    )

    assert result.allowed is True
    assert result.status == "evaluated"
    assert result.score > 0
    assert result.patch_applied is False
    assert result.generated_code_executed is False
    assert result.local_brain_write is False
    assert result.production_store_mutated is False
    assert result.external_llm is False
    assert result.external_sllm is False
    assert result.metrics["particle_budget_ok"] is True


def test_splatra_evaluator_rejects_without_capability_token() -> None:
    result = SplatraCosmosEvaluator().evaluate(SplatraEvaluationRequest(), None)

    assert result.allowed is False
    assert result.status == "denied"
    assert result.score == 0.0


def test_splatra_evaluator_marks_oversized_budget_for_revision() -> None:
    kernel = CapabilityKernel()
    evaluator = SplatraCosmosEvaluator(kernel=kernel)
    token = kernel.issue("splatra_cosmos_evaluate")

    result = evaluator.evaluate(SplatraEvaluationRequest(particle_budget=999_999), token)

    assert result.allowed is True
    assert result.metrics["particle_budget_ok"] is False
    assert result.decision == "needs_revision"
