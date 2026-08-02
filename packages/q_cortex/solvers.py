from __future__ import annotations

import hashlib
import math
import random
import time
from typing import Any

from .models import QuboProblem, QuboSolution
from .qubo import constraint_penalty_trace, evaluate_solution


def _solution_id(problem_id: str, solver: str, selected: set[str]) -> str:
    seed = f"{problem_id}:{solver}:{','.join(sorted(selected))}"
    return f"qsol_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:18]}"


class GreedyBaselineSolver:
    name = "greedy_baseline"

    def solve_qubo(self, problem: QuboProblem, seed: int = 42, max_iterations: int = 1, **_: Any) -> QuboSolution:
        start = time.perf_counter()
        variables = [row.name for row in problem.variables]
        selected: set[str] = set()
        best_energy = evaluate_solution(problem, selected)
        improved = True
        iterations = 0
        while improved:
            improved = False
            best_candidate: set[str] | None = None
            for name in variables:
                candidate = set(selected)
                if name in candidate:
                    candidate.remove(name)
                else:
                    candidate.add(name)
                energy = evaluate_solution(problem, candidate)
                if energy < best_energy:
                    best_energy = energy
                    best_candidate = candidate
            if best_candidate is not None:
                selected = best_candidate
                improved = True
            iterations += 1
            if iterations >= max(1, max_iterations):
                break
        return QuboSolution(
            solution_id=_solution_id(problem.problem_id, self.name, selected),
            problem_id=problem.problem_id,
            selected_variables=sorted(selected),
            objective_value=best_energy,
            solver_name=self.name,
            iterations=iterations,
            temperature_schedule=[],
            seed=seed,
            runtime_ms=(time.perf_counter() - start) * 1000,
            trace={
                "selected_count": len(selected),
                "constraint_penalties": constraint_penalty_trace(problem, selected),
                "best_energy_by_iteration": [best_energy],
            },
        )


class SimulatedAnnealingSolver:
    name = "simulated_annealing"

    def solve_qubo(
        self,
        problem: QuboProblem,
        seed: int = 42,
        max_iterations: int = 2000,
        initial_temperature: float = 2.0,
        final_temperature: float = 0.01,
    ) -> QuboSolution:
        start = time.perf_counter()
        rng = random.Random(seed)
        variables = [row.name for row in problem.variables]
        greedy = GreedyBaselineSolver().solve_qubo(problem, seed=seed, max_iterations=max(8, min(128, len(variables) * 2)))
        selected = set(greedy.selected_variables)
        current_energy = evaluate_solution(problem, selected)
        best_selected = set(selected)
        best_energy = current_energy
        accepted = 0
        rejected = 0
        best_energy_trace: list[float] = []
        temperatures: list[float] = []
        iterations = max(1, int(max_iterations))
        for iteration in range(iterations):
            if not variables:
                break
            progress = iteration / max(1, iterations - 1)
            temperature = initial_temperature * ((final_temperature / initial_temperature) ** progress)
            temperatures.append(round(temperature, 6))
            name = rng.choice(variables)
            candidate = set(selected)
            if name in candidate:
                candidate.remove(name)
            else:
                candidate.add(name)
            candidate_energy = evaluate_solution(problem, candidate)
            delta = candidate_energy - current_energy
            accept = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9))
            if accept:
                selected = candidate
                current_energy = candidate_energy
                accepted += 1
                if current_energy < best_energy:
                    best_energy = current_energy
                    best_selected = set(selected)
            else:
                rejected += 1
            if iteration % max(1, iterations // 64) == 0:
                best_energy_trace.append(best_energy)
        return QuboSolution(
            solution_id=_solution_id(problem.problem_id, self.name, best_selected),
            problem_id=problem.problem_id,
            selected_variables=sorted(best_selected),
            objective_value=best_energy,
            solver_name=self.name,
            iterations=iterations,
            temperature_schedule=temperatures[:: max(1, len(temperatures) // 32)] if temperatures else [],
            seed=seed,
            runtime_ms=(time.perf_counter() - start) * 1000,
            trace={
                "accepted_moves": accepted,
                "rejected_moves": rejected,
                "best_energy_by_iteration": best_energy_trace,
                "selected_count": len(best_selected),
                "constraint_penalties": constraint_penalty_trace(problem, best_selected),
                "greedy_baseline": greedy.to_dict(),
            },
        )


def solve_qubo(problem: QuboProblem, solver: str = "simulated_annealing", seed: int = 42, **kwargs: Any) -> QuboSolution:
    if solver == "greedy_baseline":
        return GreedyBaselineSolver().solve_qubo(problem, seed=seed, **kwargs)
    return SimulatedAnnealingSolver().solve_qubo(problem, seed=seed, **kwargs)
