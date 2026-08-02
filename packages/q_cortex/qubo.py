from __future__ import annotations

import hashlib
from typing import Any

from .models import QuboObjectiveTerm, QuboProblem, QuboVariable


MINIMIZATION_CONVENTION = (
    "Q-Cortex minimizes QUBO energy. Positive item rewards are represented as negative linear coefficients; "
    "risk, contradiction, budget, diversity, and dependency violations are positive penalties."
)


def _problem_id(problem_type: str, variables: list[QuboVariable], metadata: dict[str, Any]) -> str:
    seed = "|".join([problem_type, ",".join(row.name for row in variables), str(sorted(metadata.items()))])
    return f"qubo_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:18]}"


def build_qubo_problem(
    variables: list[QuboVariable],
    linear_rewards: dict[str, float],
    pairwise_terms: dict[tuple[str, str], float],
    constraints: dict[str, Any],
    problem_type: str,
    metadata: dict[str, Any],
) -> QuboProblem:
    linear_terms = [
        QuboObjectiveTerm(var_a=name, var_b=None, coefficient=-float(reward), reason="reward")
        for name, reward in sorted(linear_rewards.items())
    ]
    quadratic_terms = [
        QuboObjectiveTerm(var_a=a, var_b=b, coefficient=float(coef), reason="pairwise_penalty_or_bonus")
        for (a, b), coef in sorted(pairwise_terms.items())
    ]
    return QuboProblem(
        problem_id=_problem_id(problem_type, variables, metadata),
        problem_type=problem_type,  # type: ignore[arg-type]
        variables=variables,
        linear_terms=linear_terms,
        quadratic_terms=quadratic_terms,
        constraints={**constraints, "energy_convention": MINIMIZATION_CONVENTION},
        metadata=metadata,
    )


def _constraint_penalties(problem: QuboProblem, selected_variables: set[str]) -> dict[str, float]:
    constraints = problem.constraints or {}
    penalty_weight = float(constraints.get("penalty_weight", 4.0))
    penalties: dict[str, float] = {}
    count = len(selected_variables)
    max_selected = constraints.get("max_selected")
    min_selected = constraints.get("min_selected")
    if isinstance(max_selected, int) and count > max_selected:
        penalties["max_selected"] = ((count - max_selected) ** 2) * penalty_weight
    if isinstance(min_selected, int) and count < min_selected:
        penalties["min_selected"] = ((min_selected - count) ** 2) * penalty_weight

    variables = {row.name: row for row in problem.variables}
    group_key = constraints.get("group_diversity_key")
    if group_key:
        group_counts: dict[str, int] = {}
        for name in selected_variables:
            group = str(variables.get(name, QuboVariable(name, "node", name)).metadata.get(group_key, "unknown"))
            group_counts[group] = group_counts.get(group, 0) + 1
        penalties["group_diversity"] = sum(max(0, count - 1) ** 2 for count in group_counts.values()) * float(constraints.get("group_penalty", 0.18))

    budget_points = constraints.get("budget_points")
    if isinstance(budget_points, int):
        budget = 0
        for name in selected_variables:
            budget += int(variables.get(name, QuboVariable(name, "node", name)).metadata.get("cost_points", 0) or 0)
        if budget > budget_points:
            penalties["budget"] = ((budget - budget_points) ** 2) * float(constraints.get("budget_penalty", 0.08))

    dependencies = constraints.get("dependencies") or {}
    if isinstance(dependencies, dict):
        missing = 0
        for name, deps in dependencies.items():
            if name in selected_variables:
                missing += sum(1 for dep in deps if dep not in selected_variables)
        if missing:
            penalties["dependencies"] = missing * float(constraints.get("dependency_penalty", 2.5))
    return penalties


def evaluate_solution(problem: QuboProblem, selected_variables: set[str]) -> float:
    energy = 0.0
    for term in problem.linear_terms:
        if term.var_a in selected_variables:
            energy += term.coefficient
    for term in problem.quadratic_terms:
        if term.var_a in selected_variables and term.var_b in selected_variables:
            energy += term.coefficient
    energy += sum(_constraint_penalties(problem, selected_variables).values())
    return energy


def constraint_penalty_trace(problem: QuboProblem, selected_variables: set[str]) -> dict[str, float]:
    return _constraint_penalties(problem, selected_variables)
