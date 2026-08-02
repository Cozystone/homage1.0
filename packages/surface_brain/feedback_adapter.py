from __future__ import annotations

from pathlib import Path
from typing import Any

from .repair_rules import RepairRule, stable_rule_id
from .review_queue import enqueue_repair_candidates
from .storage import SURFACE_ROOT, ensure_dirs, write_json


def _feedback_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("feedback_id") or item.get("prompt_id") or f"feedback_{index}")


def convert_answer_quality_feedback_to_repair_candidates(
    feedback_items: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    ensure_dirs()
    candidates: list[RepairRule] = []
    for index, item in enumerate(feedback_items):
        feedback_type = str(item.get("type") or "")
        suggestion = str(item.get("suggestion") or "")
        flags = {str(flag) for flag in item.get("flags") or []}
        feedback_id = _feedback_id(item, index)
        joined = f"{feedback_type} {suggestion} {' '.join(flags)}".lower()
        if "trace_leakage" in joined or "internal_path" in joined or "internal" in joined:
            candidates.append(RepairRule(
                rule_id=stable_rule_id("feedback_internal_trace_leakage", [feedback_id]),
                name="feedback_internal_trace_leakage",
                description="Answer Quality detected internal route leakage; move implementation details to trace.",
                trigger_terms=["Local Brain", "Cloud Brain", "Working Memory", "Q-Cortex", "source_hash", "node_id", "attach", "detach"],
                mode_scope="default_only",
                action="move_to_trace",
                severity="high",
                enabled=True,
                source="answer_quality_feedback",
                created_from_feedback_id=feedback_id,
            ))
        elif "template" in joined or "diversity" in joined:
            candidates.append(RepairRule(
                rule_id=stable_rule_id("feedback_construction_diversity_hint", [feedback_id]),
                name="feedback_construction_diversity_hint",
                description="Review-only construction diversity hint. This is not automatically enabled as a text repair.",
                trigger_terms=["쉽게 말하면", "In simple terms", "The key point is"],
                mode_scope="default_only",
                action="soften",
                replacement=None,
                severity="low",
                enabled=False,
                source="answer_quality_feedback",
                created_from_feedback_id=feedback_id,
            ))
        elif "korean" in joined or "language" in joined or "unnatural" in joined:
            candidates.append(RepairRule(
                rule_id=stable_rule_id("feedback_language_style_hint", [feedback_id]),
                name="feedback_language_style_hint",
                description="Review-only language naturalness hint. Keep disabled until manually reviewed.",
                trigger_terms=[],
                mode_scope="default_only",
                action="rewrite_sentence",
                replacement=None,
                severity="medium",
                enabled=False,
                source="answer_quality_feedback",
                created_from_feedback_id=feedback_id,
            ))
        elif "grounding" in joined:
            candidates.append(RepairRule(
                rule_id=stable_rule_id("feedback_grounding_guard_hint", [feedback_id]),
                name="feedback_grounding_guard_hint",
                description="Review-only semantic support check hint. This should not rewrite text directly.",
                trigger_terms=[],
                mode_scope="default_only",
                action="move_to_trace",
                replacement=None,
                severity="medium",
                enabled=False,
                source="answer_quality_feedback",
                created_from_feedback_id=feedback_id,
            ))
    rows = [candidate.to_dict() for candidate in candidates]
    path = store_repair_candidates(run_id, rows)
    for row in rows:
        row["stored_path"] = str(path)
    return rows


def store_repair_candidates(run_id: str, candidates: list[dict[str, Any]]) -> Path:
    ensure_dirs()
    path = SURFACE_ROOT / "repair_candidates" / f"repair_candidates_{run_id}.json"
    write_json(path, {
        "run_id": run_id,
        "candidates": candidates,
        "auto_promoted": False,
        "review_required": True,
    })
    return path


def convert_feedback_and_enqueue_candidates(
    feedback_items: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    candidates = convert_answer_quality_feedback_to_repair_candidates(feedback_items, run_id)
    queued = enqueue_repair_candidates(candidates, source_run_id=run_id)
    queue_path = str(SURFACE_ROOT / "review_queue")
    return {
        "created_candidates": len(queued),
        "candidate_ids": [str(item.get("candidate_id")) for item in queued],
        "candidates": queued,
        "queue_path": queue_path,
        "requires_review": True,
        "auto_promoted": False,
    }
