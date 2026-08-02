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


def _run_id(claim_id: str, evidence_items: list[dict[str, Any]], seed: int) -> str:
    raw = f"evidence:{claim_id}:{seed}:{','.join(str(row.get('id')) for row in evidence_items)}:{now_iso()}"
    return f"qco_evi_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:18]}"


def _reward(item: dict[str, Any]) -> float:
    relation_bonus = {"supports": 0.18, "qualifies": 0.1, "contradicts": 0.06, "unknown": -0.08}.get(str(item.get("relation")), 0.0)
    return (
        _f(item, "trust") * 1.2
        + _f(item, "source_reputation") * 0.95
        + _f(item, "specificity") * 0.72
        + _f(item, "recency") * 0.42
        + _f(item, "independence") * 0.75
        + (0.25 if item.get("seed_aligned") else -0.1)
        + relation_bonus
    )


def resolve_evidence_conflicts(
    claim_id: str,
    evidence_items: list[dict[str, Any]],
    max_evidence: int = 12,
    seed: int = 42,
    solver: str = "simulated_annealing",
) -> dict[str, Any]:
    variables = [
        QuboVariable(name=f"evidence:{item.get('id', index)}", kind="evidence", ref_id=str(item.get("id", index)), metadata=item)
        for index, item in enumerate(evidence_items)
    ]
    rewards = {variable.name: _reward(variable.metadata) for variable in variables}
    by_id = {str(variable.metadata.get("id", variable.ref_id)): variable for variable in variables}
    pairwise: dict[tuple[str, str], float] = {}
    for left_index, left in enumerate(variables):
        left_id = str(left.metadata.get("id", left.ref_id))
        for right in variables[left_index + 1 :]:
            right_id = str(right.metadata.get("id", right.ref_id))
            coef = 0.0
            if right_id in (left.metadata.get("conflicts_with") or []) or left_id in (right.metadata.get("conflicts_with") or []):
                coef += 3.5
            if right_id in (left.metadata.get("duplicates") or []) or left_id in (right.metadata.get("duplicates") or []):
                coef += 1.8
            if left.metadata.get("source_id") and left.metadata.get("source_id") == right.metadata.get("source_id"):
                coef += 0.25
            if {left.metadata.get("relation"), right.metadata.get("relation")} == {"supports", "contradicts"}:
                coef += 0.75
            if coef:
                pairwise[(left.name, right.name)] = coef
    problem = build_qubo_problem(
        variables,
        rewards,
        pairwise,
        {
            "max_selected": max(1, min(int(max_evidence), len(variables))),
            "min_selected": 1 if variables else 0,
            "group_diversity_key": "source_id",
            "group_penalty": 0.12,
            "penalty_weight": 4.0,
        },
        "evidence_consistency",
        {"claim_id": claim_id},
    )
    solution = solve_qubo(problem, solver=solver, seed=seed, max_iterations=1400)
    greedy = GreedyBaselineSolver().solve_qubo(problem, seed=seed, max_iterations=128)
    selected_names = set(solution.selected_variables)
    selected_items = [variable.metadata for variable in variables if variable.name in selected_names]
    rejected_items = []
    for variable in variables:
        if variable.name in selected_names:
            continue
        reason = "lower_consistency"
        item_id = str(variable.metadata.get("id", variable.ref_id))
        if any(item_id in (selected.get("conflicts_with") or []) for selected in selected_items):
            reason = "conflicts_with_selected"
        if any(item_id in (selected.get("duplicates") or []) for selected in selected_items):
            reason = "duplicate_evidence"
        rejected_items.append({**variable.metadata, "reject_reason": reason})
    conflicts = 0
    duplicates = 0
    selected_ids = {str(item.get("id")) for item in selected_items}
    sources = {str(item.get("source_id")) for item in selected_items if item.get("source_id")}
    for item in selected_items:
        conflicts += sum(1 for ref in item.get("conflicts_with") or [] if ref in selected_ids)
        duplicates += sum(1 for ref in item.get("duplicates") or [] if ref in selected_ids)
    contradiction_score = min(1.0, conflicts / max(1, len(selected_items)))
    consistency_score = max(0.0, 1.0 - contradiction_score - duplicates * 0.08)
    status = "evidence_backed" if selected_items and contradiction_score < 0.2 else "contradiction_pending" if selected_items else "rejected_no_evidence"
    result = QCortexRunResult(
        run_id=_run_id(claim_id, evidence_items, seed),
        problem_type="evidence_consistency",
        solver_name=solution.solver_name,
        input_count=len(evidence_items),
        selected_count=len(selected_items),
        objective_value=solution.objective_value,
        selected_items=selected_items,
        rejected_items=rejected_items,
        honesty=honesty_flags(),
        trace={
            "claim_id": claim_id,
            "problem": problem.to_dict(),
            "solution": solution.to_dict(),
            "greedy_baseline_objective": greedy.objective_value,
            "baseline_delta": greedy.objective_value - solution.objective_value,
            "consistency_score": round(consistency_score, 4),
            "contradiction_score": round(contradiction_score, 4),
            "source_diversity_score": round(len(sources) / max(1, len(selected_items)), 4),
            "verification_route": status,
            "known_ids": sorted(by_id.keys()),
        },
    ).to_dict()
    record_run(result, "evidence_runs.jsonl")
    return result
