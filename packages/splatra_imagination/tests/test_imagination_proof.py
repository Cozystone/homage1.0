from __future__ import annotations

from packages.splatra_imagination.proof import run_imagination_proof


def test_imagination_proof_keeps_safety_flags() -> None:
    proof = run_imagination_proof(particle_budget=240)

    assert proof["passed"] is True
    assert len(proof["archetypes"]) == 9
    assert proof["safety_flags"]["external_llm"] is False
    assert proof["safety_flags"]["image_model_used"] is False
    assert proof["safety_flags"]["local_brain_write"] is False
    assert proof["safety_flags"]["production_store_mutated"] is False
    assert proof["safety_flags"]["generated_scene_committed"] is False
