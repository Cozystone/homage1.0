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


def _reward(step: dict[str, Any]) -> float:
    return (
        _f(step, "user_value") * 1.25
        + _f(step, "technical_proof_value") * 1.05
        + _f(step, "strategic_value") * 0.9
        + len(step.get("unblocks") or []) * 0.16
        + (1.0 - _f(step, "time_to_demo")) * 0.42
        + _f(step, "confidence") * 0.85
        - _f(step, "difficulty") * 0.82
        - _f(step, "risk") * 1.0
        - min(1.0, float(step.get("cost_points") or 0) / 100.0) * 0.62
    )


def optimize_roadmap(
    plan_steps: list[dict[str, Any]],
    max_steps: int = 6,
    budget_points: int = 100,
    seed: int = 42,
    solver: str = "simulated_annealing",
) -> dict[str, Any]:
    variables = [
        QuboVariable(name=f"step:{item.get('id', index)}", kind="plan_step", ref_id=str(item.get("id", index)), metadata=item)
        for index, item in enumerate(plan_steps)
    ]
    rewards = {variable.name: _reward(variable.metadata) for variable in variables}
    id_to_var = {str(variable.metadata.get("id", variable.ref_id)): variable.name for variable in variables}
    pairwise: dict[tuple[str, str], float] = {}
    dependencies: dict[str, list[str]] = {}
    for variable in variables:
        conflicts = set(variable.metadata.get("conflicts_with") or [])
        for other in variables:
            if other is variable:
                continue
            other_id = str(other.metadata.get("id", other.ref_id))
            if other_id in conflicts:
                pairwise[tuple(sorted((variable.name, other.name)))] = 2.4
        deps = [id_to_var[dep] for dep in variable.metadata.get("dependencies", []) if dep in id_to_var]
        if deps:
            dependencies[variable.name] = deps
    problem = build_qubo_problem(
        variables,
        rewards,
        pairwise,
        {
            "max_selected": max(1, min(int(max_steps), len(variables))),
            "min_selected": 1 if variables else 0,
            "budget_points": int(budget_points),
            "budget_penalty": 0.08,
            "dependencies": dependencies,
            "dependency_penalty": 2.5,
            "penalty_weight": 4.0,
        },
        "planning",
        {"budget_points": budget_points, "max_steps": max_steps},
    )
    solution = solve_qubo(problem, solver=solver, seed=seed, max_iterations=1500)
    greedy = GreedyBaselineSolver().solve_qubo(problem, seed=seed, max_iterations=128)
    selected_names = set(solution.selected_variables)
    selected_items = [variable.metadata for variable in variables if variable.name in selected_names]
    selected_items.sort(key=lambda item: (len(item.get("dependencies") or []), item.get("time_to_demo", 1.0), -_reward(item)))
    rejected_items = []
    for variable in variables:
        if variable.name in selected_names:
            continue
        reason = "outside_budget_or_lower_value"
        if variable.metadata.get("risk", 0) > 0.75:
            reason = "high_risk"
        if variable.metadata.get("dependencies"):
            reason = "dependency_or_ordering"
        rejected_items.append({**variable.metadata, "reject_reason": reason})
    budget_used = sum(int(item.get("cost_points") or 0) for item in selected_items)
    risk_score = round(sum(_f(item, "risk") for item in selected_items) / max(1, len(selected_items)), 4)
    result = QCortexRunResult(
        run_id=f"qco_plan_{hashlib.sha256(f'{seed}:{now_iso()}:{len(plan_steps)}'.encode('utf-8')).hexdigest()[:18]}",
        problem_type="planning",
        solver_name=solution.solver_name,
        input_count=len(plan_steps),
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
            "budget_used": budget_used,
            "risk_score": risk_score,
            "order_suggestion": [item.get("id") for item in selected_items],
            "next_single_recommended_step": selected_items[0] if selected_items else None,
            "autonomous_code_changes": False,
        },
    ).to_dict()
    record_run(result, "planning_runs.jsonl")
    return result
