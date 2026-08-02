from __future__ import annotations

import hashlib
from typing import Any

from .crystal_store import maybe_create_crystal
from .models import SelfQuestion
from .storage import DEFAULT_CORTEX_ROOT, append_jsonl, ensure_cortex_dirs, now_iso, read_jsonl


def _question_id(seed: str) -> str:
    return f"sq_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _question_from_trace(trace: dict[str, Any], index: int) -> SelfQuestion:
    errors = [row for row in trace.get("prediction_errors", []) if isinstance(row, dict)]
    concepts = []
    for row in errors[:4]:
        for key in ("source_concept", "target_concept", "relation"):
            if row.get(key):
                concepts.append(str(row[key]))
    if errors:
        source = "missing_evidence" if any(row.get("error_reason") == "expected_path_missing" for row in errors) else "uncertainty"
        question = f"What evidence would reduce prediction error for {' / '.join(concepts[:3]) or trace.get('query', 'this path')}?"
    else:
        source = "novelty_gap"
        question = f"What adjacent evidence could improve reuse of {trace.get('query', 'this reasoning path')}?"
    return SelfQuestion(
        question_id=_question_id(f"{trace.get('trace_id')}:{index}:{question}"),
        question=question,
        generated_from=source,  # type: ignore[arg-type]
        related_concepts=concepts[:8],
        requires_evidence=True,
        status="pending",
    )


def run_self_dream_cycle(max_questions: int = 10) -> dict[str, Any]:
    ensure_cortex_dirs()
    max_questions = max(0, min(int(max_questions), 50))
    traces = read_jsonl(DEFAULT_CORTEX_ROOT / "prediction_traces.jsonl", limit=100)
    questions: list[dict[str, Any]] = []
    crystal_candidates: list[dict[str, Any]] = []
    for index, trace in enumerate(reversed(traces)):
        if len(questions) >= max_questions:
            break
        question = _question_from_trace(trace, index).to_dict()
        observed = trace.get("observed_paths", [])
        if observed:
            question["status"] = "answered_with_evidence"
            crystal = maybe_create_crystal(trace, {"query": trace.get("query"), "active_nodes": [], "active_edges": [], "seed_anchors": [{"node_id": "seed"}], "cloud_attached_nodes": [{"node_id": "cloud"}], "salience_top_k": []})
            if crystal.get("created"):
                crystal_candidates.append(crystal)
        else:
            question["status"] = "rejected_no_evidence"
        questions.append(question)
        append_jsonl(DEFAULT_CORTEX_ROOT / "dream_questions.jsonl", {**question, "recorded_at": now_iso()})
    result = {
        "state": "completed",
        "max_questions": max_questions,
        "questions": questions,
        "question_count": len(questions),
        "crystal_candidates": crystal_candidates,
        "bounded": True,
        "self_generated_truth_saved": False,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
    }
    return result
