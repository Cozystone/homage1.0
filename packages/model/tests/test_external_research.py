from model import GLM_52_RESEARCH_CANDIDATE, external_candidate_policy_snapshot


def test_glm_52_is_registered_as_research_candidate_not_answer_engine():
    candidate = GLM_52_RESEARCH_CANDIDATE

    assert candidate.model_id == "zai-org/GLM-5.2"
    assert candidate.license_name == "MIT"
    assert candidate.default_enabled is False
    assert candidate.answer_path_allowed is False
    assert candidate.external_llm_used_if_enabled is True
    assert "offline_teacher" in candidate.allowed_uses
    assert "architecture_reference" in candidate.allowed_uses


def test_external_candidate_policy_preserves_atanor_default_invariants():
    snapshot = external_candidate_policy_snapshot("zai-org/GLM-5.2")

    assert snapshot["atanor_default_answer_path_unchanged"] is True
    assert snapshot["runtime_answer_provider"] is False
    assert snapshot["requires_explicit_research_gate"] is True
    assert snapshot["must_report_external_llm_used_if_invoked"] is True
    assert snapshot["production_store_mutation_allowed"] is False
    assert snapshot["local_brain_write_allowed"] is False
    assert snapshot["candidate_promotion_allowed"] is False
