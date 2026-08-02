from __future__ import annotations

import hashlib
from typing import Any

from .models import QCortexRunResult, QuboVariable, honesty_flags
from .qubo import build_qubo_problem
from .solvers import GreedyBaselineSolver, solve_qubo
from .storage import now_iso, record_run


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(row.get(key, default))))
    except (TypeError, ValueError):
        return default


def _reward(item: dict[str, Any], mode: str) -> float:
    mode_distance = 0.55 if mode == "far_walk" else 0.28 if mode == "analogy_walk" else 0.12
    source_penalty = 0.65 if not item.get("source_trace") else 0.0
    fact_penalty = 1.2 if item.get("is_fact_claim") else 0.0
    return (
        _f(item, "novelty") * 0.9
        + _f(item, "usefulness") * 1.05
        + _f(item, "feasibility") * 0.85
        + _f(item, "atanor_fit") * 0.82
        + _f(item, "distance") * mode_distance
        - _f(item, "risk") * 0.95
        - _f(item, "cost") * 0.5
        - source_penalty
        - fact_penalty
    )


def sample_creative_paths(
    prompt: str,
    candidate_paths: list[dict[str, Any]],
    mode: str = "far_walk",
    max_paths: int = 8,
    seed: int = 42,
    solver: str = "simulated_annealing",
) -> dict[str, Any]:
    variables = [
        QuboVariable(name=f"path:{item.get('id', index)}", kind="creative_path", ref_id=str(item.get("id", index)), metadata=item)
        for index, item in enumerate(candidate_paths)
    ]
    rewards = {variable.name: _reward(variable.metadata, mode) for variable in variables}
    pairwise: dict[tuple[str, str], float] = {}
    for left_index, left in enumerate(variables):
        left_domains = set(left.metadata.get("domains") or [])
        for right in variables[left_index + 1 :]:
            overlap = len(left_domains.intersection(set(right.metadata.get("domains") or [])))
            if overlap:
                pairwise[(left.name, right.name)] = 0.22 * overlap
    problem = build_qubo_problem(
        variables,
        rewards,
        pairwise,
        {"max_selected": max(1, min(int(max_paths), len(variables))), "min_selected": 1 if variables else 0, "penalty_weight": 4.0},
        "creative_sampling",
        {"prompt": prompt, "mode": mode},
    )
    solution = solve_qubo(problem, solver=solver, seed=seed, max_iterations=1200)
    greedy = GreedyBaselineSolver().solve_qubo(problem, seed=seed, max_iterations=128)
    selected_names = set(solution.selected_variables)
    selected_items = []
    rejected_items = []
    for variable in variables:
        critic_score = round(max(0.0, rewards.get(variable.name, 0.0)) / 4.0, 4)
        item = {**variable.metadata, "critic_score": critic_score, "stored_as_truth": False, "stored_as_idea_candidate": True}
        if variable.name in selected_names:
            selected_items.append(item)
        else:
            reason = "lower_candidate_score"
            if variable.metadata.get("is_fact_claim"):
                reason = "fact_claim_not_allowed"
            elif not variable.metadata.get("source_trace"):
                reason = "missing_source_trace"
            rejected_items.append({**item, "reject_reason": reason})
    result = QCortexRunResult(
        run_id=f"qco_cre_{hashlib.sha256(f'{prompt}:{mode}:{seed}:{now_iso()}'.encode('utf-8')).hexdigest()[:18]}",
        problem_type="creative_sampling",
        solver_name=solution.solver_name,
        input_count=len(candidate_paths),
        selected_count=len(selected_items),
        objective_value=solution.objective_value,
        selected_items=selected_items,
        rejected_items=rejected_items,
        honesty=honesty_flags(),
        trace={
            "mode": mode,
            "problem": problem.to_dict(),
            "solution": solution.to_dict(),
            "greedy_baseline_objective": greedy.objective_value,
            "baseline_delta": greedy.objective_value - solution.objective_value,
            "novelty_score": round(sum(_f(item, "novelty") for item in selected_items) / max(1, len(selected_items)), 4),
            "feasibility_score": round(sum(_f(item, "feasibility") for item in selected_items) / max(1, len(selected_items)), 4),
            "diversity_score": round(len({domain for item in selected_items for domain in item.get("domains", [])}) / max(1, len(selected_items)), 4),
            "stored_as_truth": False,
            "stored_as_idea_candidate": True,
        },
    ).to_dict()
    record_run(result, "creative_runs.jsonl")
    return result
