from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ProblemType = Literal["salience", "evidence_consistency", "creative_sampling", "planning"]
VariableKind = Literal["node", "edge", "evidence", "creative_path", "plan_step"]


def honesty_flags() -> dict[str, bool]:
    return {
        "real_quantum_hardware_used": False,
        "quantum_inspired_only": True,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }


@dataclass(slots=True)
class QuboVariable:
    name: str
    kind: VariableKind
    ref_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuboObjectiveTerm:
    var_a: str
    var_b: str | None
    coefficient: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuboProblem:
    problem_id: str
    problem_type: ProblemType
    variables: list[QuboVariable]
    linear_terms: list[QuboObjectiveTerm]
    quadratic_terms: list[QuboObjectiveTerm]
    constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "problem_type": self.problem_type,
            "variables": [row.to_dict() for row in self.variables],
            "linear_terms": [row.to_dict() for row in self.linear_terms],
            "quadratic_terms": [row.to_dict() for row in self.quadratic_terms],
            "constraints": self.constraints,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class QuboSolution:
    solution_id: str
    problem_id: str
    selected_variables: list[str]
    objective_value: float
    solver_name: str
    iterations: int
    temperature_schedule: list[float]
    seed: int | None
    runtime_ms: float
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QCortexRunResult:
    run_id: str
    problem_type: str
    solver_name: str
    input_count: int
    selected_count: int
    objective_value: float
    selected_items: list[dict[str, Any]]
    rejected_items: list[dict[str, Any]]
    honesty: dict[str, bool] = field(default_factory=honesty_flags)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
