from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spark_chamber.entropy import make_deterministic_entropy
from packages.spark_chamber.models import ChaosBudget, MutationEvent, MutationType, SparkInput


def _risk(mutation_type: MutationType) -> float:
    return {
        "phase_jitter": 0.08,
        "relation_swap": 0.16,
        "priority_jitter": 0.1,
        "symbolic_gap": 0.14,
        "contradiction_probe": 0.18,
        "virtual_bit_flip": 0.4,
    }[mutation_type]


def apply_mutation(input_event: SparkInput, budget: ChaosBudget, mutation_type: MutationType) -> MutationEvent:
    """Apply one sandboxed mutation to a deep copy of the fixture content."""

    if input_event.metadata.get("target") in {"production", "local_brain", "candidate_store"}:
        raise ValueError("Spark Chamber cannot target production, Local Brain, or candidate store")
    if mutation_type == "virtual_bit_flip" and not budget.allow_bit_flip:
        raise ValueError("virtual bit flip blocked by chaos budget")
    if mutation_type == "relation_swap" and not budget.allow_relation_swap:
        raise ValueError("relation swap blocked by chaos budget")
    if mutation_type == "phase_jitter" and not budget.allow_phase_jitter:
        raise ValueError("phase jitter blocked by chaos budget")
    if mutation_type == "priority_jitter" and not budget.allow_priority_jitter:
        raise ValueError("priority jitter blocked by chaos budget")
    risk_score = _risk(mutation_type)
    if risk_score > budget.max_risk_score:
        raise ValueError("mutation risk exceeds chaos budget")
    before = deepcopy(input_event.content)
    after = deepcopy(input_event.content)
    rng = make_deterministic_entropy(input_event.deterministic_seed)

    if mutation_type == "phase_jitter":
        phase = float(after.get("phase", 0.0))
        after["phase"] = round(phase + (rng.random() - 0.5) * budget.max_mutation_rate, 6)
    elif mutation_type == "relation_swap":
        relations = list(after.get("relations", []))
        if len(relations) >= 2:
            relations[0], relations[1] = relations[1], relations[0]
        after["relations"] = relations
    elif mutation_type == "priority_jitter":
        priorities = list(after.get("priorities", []))
        if len(priorities) >= 2:
            first = priorities.pop(0)
            priorities.append(first)
        after["priorities"] = priorities
    elif mutation_type == "symbolic_gap":
        optional = list(after.get("optional_fields", []))
        if optional:
            after["symbolic_gap_removed"] = optional.pop(0)
            after["optional_fields"] = optional
    elif mutation_type == "contradiction_probe":
        after.setdefault("contradictions", []).append({"claim": "A", "negates": "A", "fixture_only": True})
    elif mutation_type == "virtual_bit_flip":
        bits = list(str(after.get("bits", "0")))
        if bits:
            bits[0] = "1" if bits[0] == "0" else "0"
        after["bits"] = "".join(bits)

    changed = sum(1 for key in set(before) | set(after) if before.get(key) != after.get(key))
    if changed > budget.max_mutated_fields:
        raise ValueError("mutation changed too many fields")
    return MutationEvent(
        f"mutation_{input_event.input_id}_{mutation_type}",
        mutation_type,
        before,
        after,
        risk_score=risk_score,
        reversible=True,
    )


def generate_mutations(input_event: SparkInput, budget: ChaosBudget) -> tuple[list[MutationEvent], int]:
    events: list[MutationEvent] = []
    rejected = 0
    for mutation_type in ("phase_jitter", "relation_swap", "priority_jitter", "symbolic_gap", "contradiction_probe", "virtual_bit_flip"):
        try:
            events.append(apply_mutation(input_event, budget, mutation_type))  # type: ignore[arg-type]
        except ValueError:
            rejected += 1
    return events, rejected
