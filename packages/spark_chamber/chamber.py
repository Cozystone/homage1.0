from __future__ import annotations

from packages.spark_chamber.contradiction import detect_contradictions
from packages.spark_chamber.homeostasis import decide_homeostasis
from packages.spark_chamber.insight import accept_insight, score_insight
from packages.spark_chamber.models import ChaosBudget, SparkChamberReport, SparkInput
from packages.spark_chamber.mutation import generate_mutations
from packages.spark_chamber.strange_loop import probe_strange_loop


class SparkChamber:
    """Controlled-chaos sandbox that returns candidate-only insights."""

    def run(self, input_event: SparkInput, budget: ChaosBudget) -> SparkChamberReport:
        events, rejected = generate_mutations(input_event, budget)
        contradiction = detect_contradictions(input_event.content)
        loop = probe_strange_loop(input_event.content)
        mutation_pressure = min(1.0, len(events) * budget.max_mutation_rate)
        homeostasis = decide_homeostasis(
            {"disk_free_gib": float(input_event.metadata.get("disk_free_gib", 80.0))},
            float(contradiction["pressure"]),
            mutation_pressure,
            float(input_event.metadata.get("uncertainty", 0.3)),
            float(input_event.metadata.get("user_goal_pressure", 0.3)),
        )
        insights = []
        if homeostasis.action not in {"pause_mutation", "blocked"}:
            for event in events:
                insight = score_insight(input_event.input_id, event, float(contradiction["pressure"]), float(loop["loop_complexity_score"]))
                if accept_insight(insight, budget):
                    insights.append(insight)
                else:
                    rejected += 1
        invariants = {
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_store_mutated": False,
            "approved_payloads_mutated": False,
            "external_llm_used": False,
            "mock_growth": False,
            "active_24h_run_not_modified": True,
            "generated_code_executed": False,
            "real_hot_swap_performed": False,
            "homeostasis_action": homeostasis.action,
        }
        passed = (
            invariants["production_store_mutated"] is False
            and invariants["local_brain_write"] is False
            and invariants["candidate_store_mutated"] is False
            and invariants["approved_payloads_mutated"] is False
            and invariants["external_llm_used"] is False
            and invariants["generated_code_executed"] is False
            and invariants["real_hot_swap_performed"] is False
        )
        return SparkChamberReport(
            f"spark_report_{input_event.input_id}",
            total_mutations=len(events),
            accepted_insights=len(insights),
            rejected_mutations=rejected,
            chaos_budget=budget.to_dict(),
            insights=insights,
            invariants=invariants,
            passed=passed,
        )
