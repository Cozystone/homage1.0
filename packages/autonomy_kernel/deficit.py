from __future__ import annotations

from .models import DeficitSignal, SelfModelSnapshot, WorldModelSnapshot


def _energy(severity: float, weight: float = 1.0) -> float:
    return max(0.0, min(1.0, round(severity * weight, 4)))


def compute_deficit(world: WorldModelSnapshot, self_model: SelfModelSnapshot) -> list[DeficitSignal]:
    """Compute deterministic deficit signals.

    A deficit signal is a control signal, not an emotion and not evidence of
    consciousness.
    """

    signals: list[DeficitSignal] = []
    index = 1

    for question in world.unresolved_questions:
        severity = 0.55
        signals.append(
            DeficitSignal(
                f"deficit_{index}",
                "knowledge_gap",
                severity,
                _energy(severity, 1.05),
                "world_model.unresolved_questions",
                [{"question": question}],
                "propose_research_question",
            )
        )
        index += 1

    for contradiction in world.contradictions:
        severity = float(contradiction.get("severity", 0.75))
        severity = max(0.0, min(1.0, severity))
        # A merged name and a disagreement between sources are both "contradiction" to the drive,
        # but they call for opposite repairs and were being sent to the same one. Reviewing the
        # evidence for "Athens is in Greece" and "Athens is in Zimbabwe" finds both well sourced,
        # because the defect is not in either claim -- it is that one node is carrying two places.
        # `knowledge_repair.repair_driver` is what performs the separation.
        merged = str(contradiction.get("kind", "")) == "merged_referent"
        action = ("propose_referent_separation" if merged
                  else "propose_privacy_or_evidence_review")
        signals.append(
            DeficitSignal(
                f"deficit_{index}",
                "contradiction",
                severity,
                _energy(severity, 1.15),
                "world_model.contradictions",
                [contradiction],
                action,
            )
        )
        index += 1

    for gap in world.confidence_gaps:
        confidence = float(gap.get("confidence", 1.0))
        if confidence < 0.65:
            severity = round(1.0 - confidence, 4)
            signals.append(
                DeficitSignal(
                    f"deficit_{index}",
                    "low_confidence",
                    severity,
                    _energy(severity),
                    "world_model.confidence_gaps",
                    [gap],
                    "propose_evidence_collection",
                )
            )
            index += 1

    disk_gib = float(self_model.resource_state.get("disk_free_gib", 999.0))
    ram_gib = float(self_model.resource_state.get("ram_free_gib", 999.0))
    if disk_gib < 40.0 or ram_gib < 4.0:
        severity = 0.8 if disk_gib < 20.0 or ram_gib < 2.0 else 0.55
        signals.append(
            DeficitSignal(
                f"deficit_{index}",
                "resource_pressure",
                severity,
                _energy(severity, 1.1),
                "self_model.resource_state",
                [{"disk_free_gib": disk_gib, "ram_free_gib": ram_gib}],
                "propose_resource_conservation",
            )
        )
        index += 1

    for limit in self_model.known_limits:
        kind = "promotion_needed" if "promotion" in limit.lower() else "missing_skill"
        severity = 0.5
        signals.append(
            DeficitSignal(
                f"deficit_{index}",
                kind,
                severity,
                _energy(severity, 0.9),
                "self_model.known_limits",
                [{"known_limit": limit}],
                "propose_human_review",
            )
        )
        index += 1

    progressed_goals = {str(run.get("goal", "")).lower() for run in self_model.recent_runs if run.get("status") in {"complete", "running"}}
    for goal in self_model.user_goals:
        if goal.lower() not in progressed_goals:
            severity = 0.6
            signals.append(
                DeficitSignal(
                    f"deficit_{index}",
                    "unresolved_user_goal",
                    severity,
                    _energy(severity),
                    "self_model.user_goals",
                    [{"goal": goal}],
                    "propose_next_step",
                )
            )
            index += 1

    return signals

