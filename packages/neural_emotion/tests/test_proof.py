from packages.neural_emotion.proof import run_proof


def test_proof_scenarios_pass() -> None:
    result = run_proof()

    assert result["verdict"] == "PASS"
    assert all(result["checks"].values())
    assert result["safety_flags"]["external_llm"] is False
    assert result["safety_flags"]["consciousness_claim"] is False
