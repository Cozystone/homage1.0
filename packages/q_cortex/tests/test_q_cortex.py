from __future__ import annotations

from pathlib import Path

from packages.q_cortex.creative_optimizer import sample_creative_paths
from packages.q_cortex.evidence_optimizer import resolve_evidence_conflicts
from packages.q_cortex.models import QuboVariable
from packages.q_cortex.planning_optimizer import optimize_roadmap
from packages.q_cortex.proof import write_q_cortex_optimizer_proof
from packages.q_cortex.qubo import build_qubo_problem, evaluate_solution
from packages.q_cortex.salience_optimizer import optimize_salience_workspace
from packages.q_cortex.solvers import solve_qubo


def test_qubo_energy_rewards_selection_and_penalizes_budget() -> None:
    variables = [
        QuboVariable("node:a", "node", "a", {"cost_points": 4}),
        QuboVariable("node:b", "node", "b", {"cost_points": 8}),
    ]
    problem = build_qubo_problem(
        variables,
        {"node:a": 2.0, "node:b": 1.0},
        {("node:a", "node:b"): 0.5},
        {"max_selected": 1, "budget_points": 6, "budget_penalty": 1.0, "penalty_weight": 4.0},
        "salience",
        {},
    )

    assert evaluate_solution(problem, {"node:a"}) < evaluate_solution(problem, set())
    assert evaluate_solution(problem, {"node:a", "node:b"}) > evaluate_solution(problem, {"node:a"})


def test_solver_respects_max_selected_budget() -> None:
    variables = [QuboVariable(f"node:{index}", "node", str(index), {}) for index in range(6)]
    rewards = {variable.name: 1.0 for variable in variables}
    problem = build_qubo_problem(variables, rewards, {}, {"max_selected": 2, "penalty_weight": 5.0}, "salience", {})

    solution = solve_qubo(problem, seed=7, max_iterations=300)

    assert len(solution.selected_variables) <= 2
    assert solution.solver_name == "simulated_annealing"


def test_salience_optimizer_rejects_low_trust_high_risk_noise(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"id": "seed-evidence", "kind": "node", "layer": "seed_anchor", "query_relevance": 0.95, "activation": 0.92, "trust": 0.94, "novelty": 0.2, "user_goal_fit": 0.9, "risk": 0.05, "fatigue": 0.02, "source_id": "seed", "concept_id": "Evidence"},
        {"id": "cloud-context", "kind": "node", "layer": "cloud_attached", "query_relevance": 0.82, "activation": 0.8, "trust": 0.72, "novelty": 0.3, "user_goal_fit": 0.75, "risk": 0.18, "fatigue": 0.05, "source_id": "cloud-a", "concept_id": "Context", "temporary": True},
        {"id": "noise", "kind": "node", "layer": "cloud_attached", "query_relevance": 0.1, "activation": 0.1, "trust": 0.12, "novelty": 0.95, "user_goal_fit": 0.05, "risk": 0.94, "fatigue": 0.7, "source_id": "noise", "concept_id": "Noise", "temporary": True},
    ]

    result = optimize_salience_workspace(candidates, max_nodes=2, max_edges=0, seed=11)

    assert result["selected_count"] <= 2
    assert "noise" not in {item["id"] for item in result["selected_items"]}
    assert any(item["reject_reason"] in {"high_risk", "low_trust"} for item in result["rejected_items"])
    assert result["honesty"]["real_quantum_hardware_used"] is False
    assert result["honesty"]["local_brain_write"] is False


def test_evidence_optimizer_avoids_conflicting_low_trust_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    evidence = [
        {"id": "support", "source_id": "paper-a", "relation": "supports", "trust": 0.92, "source_reputation": 0.9, "specificity": 0.88, "recency": 0.8, "independence": 0.9, "seed_aligned": True, "conflicts_with": ["contradict"], "duplicates": []},
        {"id": "independent", "source_id": "paper-b", "relation": "supports", "trust": 0.84, "source_reputation": 0.82, "specificity": 0.78, "recency": 0.7, "independence": 0.95, "seed_aligned": True, "conflicts_with": [], "duplicates": []},
        {"id": "contradict", "source_id": "blog-x", "relation": "contradicts", "trust": 0.18, "source_reputation": 0.15, "specificity": 0.2, "recency": 0.6, "independence": 0.3, "seed_aligned": False, "conflicts_with": ["support"], "duplicates": []},
    ]

    result = resolve_evidence_conflicts("claim", evidence, max_evidence=2, seed=12)

    selected_ids = {item["id"] for item in result["selected_items"]}
    assert "support" in selected_ids
    assert "contradict" not in selected_ids
    assert result["trace"]["verification_route"] == "evidence_backed"


def test_creative_optimizer_never_stores_ideas_as_truth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paths = [
        {"id": "privacy-gate", "domains": ["privacy"], "novelty": 0.6, "usefulness": 0.9, "feasibility": 0.85, "atanor_fit": 0.9, "distance": 0.4, "risk": 0.2, "cost": 0.2, "source_trace": ["vault"], "is_fact_claim": False},
        {"id": "magic-claim", "domains": ["speculative"], "novelty": 0.99, "usefulness": 0.05, "feasibility": 0.01, "atanor_fit": 0.05, "distance": 0.98, "risk": 0.95, "cost": 0.9, "source_trace": [], "is_fact_claim": True},
    ]

    result = sample_creative_paths("privacy architecture", paths, max_paths=1, seed=13)

    assert result["selected_items"][0]["stored_as_truth"] is False
    assert result["trace"]["stored_as_idea_candidate"] is True
    assert any(item["reject_reason"] == "fact_claim_not_allowed" for item in result["rejected_items"])


def test_planning_optimizer_keeps_within_budget_and_does_not_autocode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    steps = [
        {"id": "low-risk", "user_value": 0.9, "technical_proof_value": 0.8, "strategic_value": 0.8, "difficulty": 0.2, "risk": 0.2, "cost_points": 10, "dependencies": [], "conflicts_with": [], "unblocks": [], "time_to_demo": 0.2, "confidence": 0.9},
        {"id": "expensive", "user_value": 0.95, "technical_proof_value": 0.9, "strategic_value": 0.95, "difficulty": 0.8, "risk": 0.8, "cost_points": 80, "dependencies": [], "conflicts_with": [], "unblocks": [], "time_to_demo": 0.9, "confidence": 0.4},
    ]

    result = optimize_roadmap(steps, max_steps=2, budget_points=25, seed=14)

    assert result["trace"]["budget_used"] <= 25
    assert result["trace"]["autonomous_code_changes"] is False
    assert result["selected_items"]


def test_q_cortex_proof_artifacts_are_honest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = write_q_cortex_optimizer_proof()
    proof = result["proof"]

    assert proof["result"] == "PASS"
    assert "real quantum hardware usage" in proof["does_not_claim"]
    assert proof["scenarios"]["creative"]["trace"]["stored_as_truth"] is False
    assert proof["scenarios"]["planning"]["trace"]["autonomous_code_changes"] is False
    assert Path("data/q_cortex/proofs/q_cortex_optimizer_proof.json").exists()
    assert Path("data/q_cortex/proofs/q_cortex_optimizer_proof.md").exists()
