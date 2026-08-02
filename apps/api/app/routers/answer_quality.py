from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.answer_quality.benchmark_set import CORE_SET_NAME, ensure_default_benchmark_set
from packages.answer_quality.comparison import get_report, get_run, list_runs, run_answer_quality_benchmark, run_repair_comparison
from packages.answer_quality.storage import REPAIR_COMPARISON_ROOT, list_json_files, read_json
from packages.answer_quality.evaluators import evaluate_answer_quality
from packages.answer_quality.models import honesty_flags
from packages.answer_quality.proof import run_answer_quality_proof


router = APIRouter(prefix="/api/answer-quality", tags=["answer-quality"])


class AnswerQualityRunRequest(BaseModel):
    benchmark_set: str = CORE_SET_NAME
    limit: int | None = Field(default=None, ge=1, le=100)
    categories: list[str] | None = None


class AnswerQualityRepairComparisonRequest(BaseModel):
    benchmark_set: str = CORE_SET_NAME
    limit: int | None = Field(default=None, ge=1, le=100)


class EvaluateAnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    language: str = "ko"
    mode: str = "default"
    semantic_context: list[dict[str, Any]] = Field(default_factory=list)
    expected_behavior: dict[str, Any] = Field(default_factory=dict)


def _flags() -> dict[str, Any]:
    return {
        **honesty_flags(),
        "evaluation_mode": "deterministic_local_heuristic",
        "feedback_auto_promoted": False,
    }


@router.get("/status")
def answer_quality_status() -> dict[str, Any]:
    benchmark = ensure_default_benchmark_set()
    runs = list_runs(limit=5)
    latest = runs[0] if runs else None
    return {
        "state": "active",
        "label": "Answer Quality Lab",
        "benchmark_set": benchmark.get("name", CORE_SET_NAME),
        "benchmark_prompts": len(benchmark.get("prompts", [])),
        "latest_run": latest,
        "run_count": len(list_runs(limit=100)),
        "metrics": [
            "naturalness",
            "helpfulness",
            "trace_hygiene",
            "grounding",
            "template_smell",
            "style_fit",
            "language_native",
            "concision",
        ],
        **_flags(),
    }


@router.post("/run")
def answer_quality_run(request: AnswerQualityRunRequest) -> dict[str, Any]:
    return {**run_answer_quality_benchmark(request.benchmark_set, limit=request.limit, categories=request.categories), **_flags()}


@router.get("/runs")
def answer_quality_runs(limit: int = 20) -> dict[str, Any]:
    bounded = max(1, min(int(limit), 100))
    runs = list_runs(limit=bounded)
    return {"runs": runs, "count": len(runs), **_flags()}


@router.post("/run-repair-comparison")
def answer_quality_run_repair_comparison(request: AnswerQualityRepairComparisonRequest) -> dict[str, Any]:
    return {**run_repair_comparison(request.benchmark_set, limit=request.limit), **_flags()}


@router.get("/repair-comparisons")
def answer_quality_repair_comparisons(limit: int = 20) -> dict[str, Any]:
    bounded = max(1, min(int(limit), 100))
    rows = []
    for path in list_json_files(REPAIR_COMPARISON_ROOT)[:bounded]:
        rows.append(read_json(path, {}))
    return {"repair_comparisons": rows, "count": len(rows), **_flags()}


@router.get("/repair-comparisons/{run_id}")
def answer_quality_repair_comparison_detail(run_id: str) -> dict[str, Any]:
    path = REPAIR_COMPARISON_ROOT / f"repair_comparison_{run_id}.json"
    payload = read_json(path, None)
    if payload is None:
        raise HTTPException(status_code=404, detail="answer_quality_repair_comparison_not_found")
    return {**payload, **_flags()}


@router.get("/runs/{run_id}")
def answer_quality_run_detail(run_id: str) -> dict[str, Any]:
    payload = get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="answer_quality_run_not_found")
    return {**payload, **_flags()}


@router.get("/report/{run_id}")
def answer_quality_report(run_id: str) -> dict[str, Any]:
    report = get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="answer_quality_report_not_found")
    return {"run_id": run_id, "markdown": report, **_flags()}


@router.post("/evaluate-answer")
def answer_quality_evaluate_answer(request: EvaluateAnswerRequest) -> dict[str, Any]:
    score = evaluate_answer_quality(
        candidate_id="manual_eval",
        answer=request.answer,
        query=request.query,
        language=request.language,
        mode=request.mode,
        semantic_context=request.semantic_context,
        expected_behavior=request.expected_behavior,
    )
    return {**score, **_flags()}


@router.post("/proof")
def answer_quality_proof() -> dict[str, Any]:
    return {**run_answer_quality_proof(), **_flags()}
