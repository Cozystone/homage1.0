from __future__ import annotations

import hashlib
from typing import Any

from .models import QCortexRunResult, QuboVariable, honesty_flags
from .qubo import build_qubo_problem
from .solvers import GreedyBaselineSolver, solve_qubo
from .storage import now_iso, record_run


def _float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(row.get(key, default))))
    except (TypeError, ValueError):
        return default


def _run_id(candidates: list[dict[str, Any]], seed: int) -> str:
    raw = f"salience:{seed}:{','.join(str(row.get('id')) for row in candidates)}:{now_iso()}"
    return f"qco_sal_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:18]}"


def _reward(row: dict[str, Any]) -> float:
    seed_bonus = 0.16 if row.get("layer") == "seed_anchor" else 0.0
    cloud_penalty = 0.08 if row.get("temporary") and row.get("layer") == "cloud_attached" else 0.0
    low_trust_penalty = max(0.0, 0.5 - _float(row, "trust")) * 0.42
    return (
        _float(row, "query_relevance") * 1.25
        + _float(row, "activation") * 1.15
        + _float(row, "trust") * 1.0
        + _float(row, "novelty") * 0.38
        + _float(row, "user_goal_fit") * 0.72
        + seed_bonus
        - _float(row, "risk") * 1.35
        - _float(row, "fatigue") * 0.62
        - cloud_penalty
        - low_trust_penalty
    )


def optimize_salience_workspace(
    candidates: list[dict[str, Any]],
    max_nodes: int = 128,
    max_edges: int = 256,
    seed: int = 42,
    solver: str = "simulated_annealing",
) -> dict[str, Any]:
    variables: list[QuboVariable] = []
    rewards: dict[str, float] = {}
    pairwise: dict[tuple[str, str], float] = {}
    for index, item in enumerate(candidates):
        kind = "edge" if item.get("kind") == "edge" else "node"
        name = f"{kind}:{item.get('id', index)}"
        variables.append(QuboVariable(name=name, kind=kind, ref_id=str(item.get("id", name)), metadata=item))
        rewards[name] = _reward(item)
    for left_index, left in enumerate(variables):
        for right in variables[left_index + 1 :]:
            coef = 0.0
            if left.metadata.get("source_id") and left.metadata.get("source_id") == right.metadata.get("source_id"):
                coef += 0.12
            if left.metadata.get("concept_id") and left.metadata.get("concept_id") == right.metadata.get("concept_id"):
                coef += 0.08
            if left.metadata.get("layer") == "seed_anchor" and right.metadata.get("layer") == "seed_anchor":
                coef -= 0.035
            if coef:
                pairwise[(left.name, right.name)] = coef
    max_selected = max(1, min(len(variables), int(max_nodes) + int(max_edges)))
    problem = build_qubo_problem(
        variables,
        rewards,
        pairwise,
        {
            "max_selected": max_selected,
            "min_selected": min(max_selected, 1 if variables else 0),
            "group_diversity_key": "source_id",
            "group_penalty": 0.08,
            "penalty_weight": 4.0,
        },
        "salience",
        {"max_nodes": max_nodes, "max_edges": max_edges},
    )
    solution = solve_qubo(problem, solver=solver, seed=seed, max_iterations=1200)
    greedy = GreedyBaselineSolver().solve_qubo(problem, seed=seed, max_iterations=128)
    selected_names = set(solution.selected_variables)
    selected_items = []
    rejected_items = []
    for variable in variables:
        item = {**variable.metadata, "qubo_variable": variable.name, "reward": round(rewards.get(variable.name, 0.0), 4)}
        if variable.name in selected_names:
            selected_items.append(item)
        else:
            reason = "not_selected"
            if _float(variable.metadata, "risk") > 0.65:
                reason = "high_risk"
            elif _float(variable.metadata, "trust") < 0.35:
                reason = "low_trust"
            rejected_items.append({**item, "reject_reason": reason})
    result = QCortexRunResult(
        run_id=_run_id(candidates, seed),
        problem_type="salience",
        solver_name=solution.solver_name,
        input_count=len(candidates),
        selected_count=len(selected_items),
        objective_value=solution.objective_value,
        selected_items=selected_items,
        rejected_items=rejected_items,
        honesty=honesty_flags(),
        trace={
            "problem": problem.to_dict(),
            "solution": solution.to_dict(),
            "greedy_baseline_objective": greedy.objective_value,
            "baseline_delta": greedy.objective_value - solution.objective_value,
        },
    ).to_dict()
    record_run(result, "salience_runs.jsonl")
    return result
