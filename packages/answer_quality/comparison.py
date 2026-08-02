from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from packages.surface_brain.monitor import monitor_answer, repair_answer
from packages.surface_brain.realization_planner import plan_speech, realize_answer

from .benchmark_set import CORE_SET_NAME, load_benchmark_set
from .evaluators import evaluate_answer_quality
from .models import AnswerCandidate, AnswerQualityRun, honesty_flags, stable_id, utc_now_iso
from .report import write_markdown_report
from .storage import REPAIR_COMPARISON_ROOT, REPORT_ROOT, RUN_ROOT, ensure_dirs, list_json_files, read_json, write_json
from .surface_feedback import generate_surface_feedback


def _context_as_semantic(prompt: dict[str, Any]) -> dict[str, Any]:
    rows = prompt.get("semantic_context") or []
    concepts = []
    evidence = []
    relations = []
    for row in rows:
        concept = row.get("concept")
        if concept:
            concepts.append(concept)
        for claim in row.get("claims", []) if isinstance(row.get("claims"), list) else []:
            evidence.append({"snippet": str(claim), "source_hash": stable_id("ctx", str(claim))})
        for relation in row.get("relations", []) if isinstance(row.get("relations"), list) else []:
            relations.append({"source": concept or "context", "relation": str(relation), "target": str(relation)})
    return {"concepts": concepts, "relations": relations, "evidence": evidence, "confidence": 0.74 if rows else 0.3}


def _baseline_answer(prompt: dict[str, Any]) -> str:
    query = prompt["query"]
    if prompt["language"] == "ko":
        if "쿠버네티스" in query:
            return "쿠버네티스는 컨테이너를 관리하는 시스템입니다."
        if "Q-Cortex" in query:
            return "Q-Cortex는 실제 양자컴퓨터가 아니라 로컬에서 후보 선택을 최적화하는 고전적 도구입니다."
        if "GraphRAG" in query:
            return "GraphRAG는 그래프와 근거 문서를 함께 사용해 답변을 확인합니다."
        return "질문에 대해 핵심만 말하면, 관련 개념을 근거와 함께 확인해 답합니다."
    if "Kubernetes" in query:
        return "Kubernetes is a system that manages containers."
    if "Q-Cortex" in query:
        return "Q-Cortex is a local quantum-inspired optimizer, not real quantum hardware."
    return "It answers by checking relevant concepts and evidence."


def _surface_answer(prompt: dict[str, Any], *, repair: bool) -> tuple[str, dict[str, Any], str | None]:
    semantic = _context_as_semantic(prompt)
    plan = plan_speech(
        prompt["query"],
        semantic,
        language=prompt.get("language"),
        audience_level=prompt.get("audience_level", "beginner"),
        tone=prompt.get("tone", "clear"),
        mode=prompt.get("mode", "default"),
    )
    answer = realize_answer(plan, semantic, query=prompt["query"], apply_repair=repair)
    repair_meta = answer.get("repair") if isinstance(answer.get("repair"), dict) else {}
    before = str(repair_meta.get("original_answer") or answer["answer"])
    final = before
    if repair and not answer.get("repair", {}).get("applied"):
        monitor = monitor_answer(before, language=prompt.get("language", "ko"))
        final = repair_answer(before, monitor, language=prompt.get("language", "ko")) if monitor["needs_repair"] else before
    elif repair:
        final = answer["answer"]
    return final, {"surface_plan": plan, "trace_summary": answer.get("trace_summary", {}), "repair": answer.get("repair", {})}, before if repair else None


def _candidate(prompt: dict[str, Any], generator: str, answer: str, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    return AnswerCandidate(
        candidate_id=stable_id("aqc", f"{prompt['prompt_id']}:{generator}:{answer}"),
        prompt_id=prompt["prompt_id"],
        generator=generator,  # type: ignore[arg-type]
        answer=answer,
        trace=trace or {},
        metadata={"generated_at": utc_now_iso()},
    ).to_dict()


def _average(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = ["naturalness", "helpfulness", "directness", "trace_hygiene", "grounding", "template_smell", "style_fit", "language_native", "concision", "repair_success", "overall"]
    if not rows:
        return {key: 0.0 for key in keys}
    return {key: round(sum(float(row.get(key, 0.0)) for row in rows) / len(rows), 4) for key in keys}


def run_answer_quality_benchmark(
    benchmark_set: str = CORE_SET_NAME,
    *,
    limit: int | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    bench = load_benchmark_set(benchmark_set)
    prompts = list(bench.get("prompts") or [])
    if categories:
        category_set = set(categories)
        prompts = [prompt for prompt in prompts if prompt.get("category") in category_set]
    if limit:
        prompts = prompts[: max(1, int(limit))]
    run_id = stable_id("aqr", f"{benchmark_set}:{utc_now_iso()}:{len(prompts)}")
    scored_candidates: list[dict[str, Any]] = []
    recent_by_generator: dict[str, list[str]] = defaultdict(list)
    for prompt in prompts:
        baseline = _candidate(prompt, "baseline", _baseline_answer(prompt))
        surface_text, surface_trace, _ = _surface_answer(prompt, repair=False)
        surface = _candidate(prompt, "surface_brain", surface_text, surface_trace)
        repaired_text, repaired_trace, before = _surface_answer(prompt, repair=True)
        repaired = _candidate(prompt, "repaired_surface_brain", repaired_text, repaired_trace)
        for candidate in (baseline, surface, repaired):
            score = evaluate_answer_quality(
                candidate_id=candidate["candidate_id"],
                answer=candidate["answer"],
                query=prompt["query"],
                language=prompt["language"],
                mode=prompt.get("mode", "default"),
                semantic_context=prompt.get("semantic_context") or [],
                expected_behavior={**(prompt.get("expected_behavior") or {}), "audience_level": prompt.get("audience_level")},
                recent_answers=recent_by_generator[candidate["generator"]],
                before_repair=before if candidate["generator"] == "repaired_surface_brain" else None,
            )
            recent_by_generator[candidate["generator"]].append(candidate["answer"])
            scored_candidates.append({"prompt": prompt, "candidate": candidate, "score": score})
    score_rows = [item["score"] for item in scored_candidates]
    category_scores: dict[str, dict[str, float]] = {}
    for category in sorted({item["prompt"]["category"] for item in scored_candidates}):
        category_scores[category] = _average([item["score"] for item in scored_candidates if item["prompt"]["category"] == category])
    surface_feedback = generate_surface_feedback(run_id, scored_candidates)
    ranked = sorted(scored_candidates, key=lambda item: float(item["score"]["overall"]))
    regressions = []
    by_prompt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scored_candidates:
        by_prompt[item["prompt"]["prompt_id"]].append(item)
    for prompt_id, items in by_prompt.items():
        baseline = next((item for item in items if item["candidate"]["generator"] == "baseline"), None)
        surface = next((item for item in items if item["candidate"]["generator"] == "surface_brain"), None)
        if baseline and surface and float(surface["score"]["overall"]) + 0.05 < float(baseline["score"]["overall"]):
            regressions.append({"prompt_id": prompt_id, "baseline": baseline["score"]["overall"], "surface": surface["score"]["overall"], "query": baseline["prompt"]["query"]})
    run = AnswerQualityRun(
        run_id=run_id,
        benchmark_set=benchmark_set,
        total_prompts=len(prompts),
        average_scores=_average(score_rows),
        category_scores=category_scores,
        worst_cases=[_case_summary(item) for item in ranked[:5]],
        best_cases=[_case_summary(item) for item in ranked[-5:][::-1]],
        regressions=regressions[:10],
        surface_feedback=surface_feedback,
        honesty=honesty_flags(),
    ).to_dict()
    write_json(RUN_ROOT / f"{run_id}.json", {"run": run, "scored_candidates": scored_candidates})
    report_path = write_markdown_report(run, scored_candidates)
    run["report_path"] = str(report_path)
    write_json(RUN_ROOT / f"{run_id}.json", {"run": run, "scored_candidates": scored_candidates})
    return run


def _case_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_id": item["prompt"]["prompt_id"],
        "query": item["prompt"]["query"],
        "category": item["prompt"]["category"],
        "generator": item["candidate"]["generator"],
        "overall": item["score"]["overall"],
        "flags": item["score"].get("flags", []),
        "answer": item["candidate"]["answer"][:240],
    }


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for path in list_json_files(RUN_ROOT)[:limit]:
        payload = read_json(path, {})
        if payload.get("run"):
            rows.append(payload["run"])
    return rows


def get_run(run_id: str) -> dict[str, Any] | None:
    path = RUN_ROOT / f"{run_id}.json"
    return read_json(path)


def get_report(run_id: str) -> str | None:
    path = REPORT_ROOT / f"{run_id}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def run_repair_comparison(
    benchmark_set: str = CORE_SET_NAME,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    bench = load_benchmark_set(benchmark_set)
    prompts = list(bench.get("prompts") or [])
    if limit:
        prompts = prompts[: max(1, int(limit))]
    run_id = stable_id("aqrepair", f"{benchmark_set}:{utc_now_iso()}:{len(prompts)}")
    rows: list[dict[str, Any]] = []
    repairs_applied = 0
    remaining_leakages: list[dict[str, Any]] = []
    for prompt in prompts:
        surface_text, surface_trace, _ = _surface_answer(prompt, repair=False)
        repaired_text, repaired_trace, before = _surface_answer(prompt, repair=True)
        before_score = evaluate_answer_quality(
            candidate_id=stable_id("before", f"{prompt['prompt_id']}:{surface_text}"),
            answer=surface_text,
            query=prompt["query"],
            language=prompt["language"],
            mode=prompt.get("mode", "default"),
            semantic_context=prompt.get("semantic_context") or [],
            expected_behavior={**(prompt.get("expected_behavior") or {}), "audience_level": prompt.get("audience_level")},
        )
        after_score = evaluate_answer_quality(
            candidate_id=stable_id("after", f"{prompt['prompt_id']}:{repaired_text}"),
            answer=repaired_text,
            query=prompt["query"],
            language=prompt["language"],
            mode=prompt.get("mode", "default"),
            semantic_context=prompt.get("semantic_context") or [],
            expected_behavior={**(prompt.get("expected_behavior") or {}), "audience_level": prompt.get("audience_level")},
            before_repair=before,
        )
        repair_meta = repaired_trace.get("repair") if isinstance(repaired_trace.get("repair"), dict) else {}
        if repair_meta.get("applied"):
            repairs_applied += 1
        if "trace_leakage" in after_score.get("flags", []):
            remaining_leakages.append({"prompt_id": prompt["prompt_id"], "query": prompt["query"], "answer": repaired_text[:240]})
        rows.append({
            "prompt_id": prompt["prompt_id"],
            "query": prompt["query"],
            "category": prompt["category"],
            "before_answer": surface_text,
            "after_answer": repaired_text,
            "before_score": before_score,
            "after_score": after_score,
            "repair": repair_meta,
            "trace_hygiene_delta": round(float(after_score["trace_hygiene"]) - float(before_score["trace_hygiene"]), 4),
            "overall_delta": round(float(after_score["overall"]) - float(before_score["overall"]), 4),
            "naturalness_delta": round(float(after_score["naturalness"]) - float(before_score["naturalness"]), 4),
            "grounding_delta": round(float(after_score["grounding"]) - float(before_score["grounding"]), 4),
            "template_smell_delta": round(float(after_score["template_smell"]) - float(before_score["template_smell"]), 4),
        })
    before_avg = _average([row["before_score"] for row in rows])
    after_avg = _average([row["after_score"] for row in rows])
    result = {
        "run_id": run_id,
        "benchmark_set": benchmark_set,
        "total_prompts": len(prompts),
        "before_average_scores": before_avg,
        "after_average_scores": after_avg,
        "trace_hygiene_before": before_avg.get("trace_hygiene", 0.0),
        "trace_hygiene_after": after_avg.get("trace_hygiene", 0.0),
        "trace_hygiene_delta": round(after_avg.get("trace_hygiene", 0.0) - before_avg.get("trace_hygiene", 0.0), 4),
        "overall_delta": round(after_avg.get("overall", 0.0) - before_avg.get("overall", 0.0), 4),
        "repairs_applied": repairs_applied,
        "remaining_leakages": remaining_leakages[:10],
        "rows": rows,
        "auto_promoted_feedback": False,
        "honesty": honesty_flags(),
    }
    json_path = REPAIR_COMPARISON_ROOT / f"repair_comparison_{run_id}.json"
    md_path = REPAIR_COMPARISON_ROOT / f"repair_comparison_{run_id}.md"
    write_json(json_path, result)
    md_path.write_text(_repair_comparison_markdown(result), encoding="utf-8")
    result["json_path"] = str(json_path)
    result["markdown_path"] = str(md_path)
    return result


def _repair_comparison_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# ATANOR Repair Comparison {result['run_id']}",
        "",
        f"- Prompts: {result['total_prompts']}",
        f"- Trace hygiene before: {result['trace_hygiene_before']}",
        f"- Trace hygiene after: {result['trace_hygiene_after']}",
        f"- Trace hygiene delta: {result['trace_hygiene_delta']}",
        f"- Overall delta: {result['overall_delta']}",
        f"- Repairs applied: {result['repairs_applied']}",
        f"- Remaining leakages: {len(result['remaining_leakages'])}",
        "",
        "## Improved/Worsened Rows",
    ]
    for row in result.get("rows", [])[:20]:
        lines.append(f"- {row['prompt_id']}: trace_delta={row['trace_hygiene_delta']} overall_delta={row['overall_delta']}")
    lines.extend([
        "",
        "## Honesty",
        "- Deterministic repair only.",
        "- Feedback was not auto-promoted into production Surface Brain weights.",
        "- This is not GPT-level language improvement.",
    ])
    return "\n".join(lines) + "\n"
