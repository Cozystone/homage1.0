from __future__ import annotations

import json
from typing import Any

from .benchmark import build_zero_user_benchmark_v0
from .models import BENCHMARK_PATH, honesty_flags, utc_now_iso
from .zero_user_answer import answer_with_base_brain


FORBIDDEN_DEFAULT_TERMS = ["Local Brain", "Cloud Brain", "Working Memory", "Q-Cortex", "source_hash", "node_id"]


def _load_benchmark() -> dict[str, Any]:
    if not BENCHMARK_PATH.exists():
        return build_zero_user_benchmark_v0()
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def _trace_hygiene(answer: str, forbidden: list[str] | None = None) -> bool:
    forbidden = forbidden or FORBIDDEN_DEFAULT_TERMS
    return not any(term in answer for term in forbidden)


def run_zero_user_benchmark(limit: int | None = None) -> dict[str, Any]:
    benchmark = _load_benchmark()
    prompts = list(benchmark.get("prompts") or [])
    if limit:
        prompts = prompts[: max(1, min(int(limit), len(prompts)))]
    results = []
    useful_count = 0
    hygiene_count = 0
    quality_scores = []
    for prompt in prompts:
        result = answer_with_base_brain(
            str(prompt["query"]),
            language=prompt.get("language", "ko"),
            audience_level=prompt.get("audience_level", "beginner"),
            mode=prompt.get("mode", "default"),
        )
        answer = str(result.get("answer") or "")
        useful = bool(answer.strip()) and (
            prompt.get("expected_intent") == "unknown"
            or bool(result.get("semantic_context_count"))
            or "부족" in answer
            or "not contain enough" in answer
        )
        hygiene = _trace_hygiene(answer, prompt.get("forbidden_leakage_terms"))
        if useful:
            useful_count += 1
        if hygiene:
            hygiene_count += 1
        quality_score = None
        try:
            from packages.answer_quality.evaluators import evaluate_answer_quality

            quality_score = evaluate_answer_quality(
                candidate_id=f"base_{prompt['prompt_id']}",
                answer=answer,
                query=str(prompt["query"]),
                language=prompt.get("language", "ko"),
                mode=prompt.get("mode", "default"),
                semantic_context=result.get("trace", {}).get("matched_concepts", []),
                expected_behavior={"length": "short" if "짧게" in str(prompt["query"]) else "normal"},
            )
            quality_scores.append(float(quality_score.get("overall") or 0.0))
        except Exception as exc:
            quality_score = {"available": False, "error": str(exc)}
        results.append(
            {
                "prompt_id": prompt["prompt_id"],
                "query": prompt["query"],
                "answer": answer,
                "useful": useful,
                "trace_hygiene": hygiene,
                "semantic_context_count": result.get("semantic_context_count", 0),
                "surface_candidate_count": result.get("surface_candidate_count", 0),
                "quality_score": quality_score,
            }
        )
    total = len(prompts)
    return {
        "run_id": f"base_benchmark_{utc_now_iso().replace(':', '').replace('-', '')}",
        "benchmark_id": benchmark.get("benchmark_id", "zero_user_general_v0"),
        "total_prompts": total,
        "useful_answer_count": useful_count,
        "trace_hygiene_count": hygiene_count,
        "useful_answer_rate": useful_count / total if total else 0.0,
        "trace_hygiene_rate": hygiene_count / total if total else 0.0,
        "average_answer_quality": sum(quality_scores) / len(quality_scores) if quality_scores else None,
        "results": results,
        **honesty_flags(),
    }
