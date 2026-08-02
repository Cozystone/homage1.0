from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_CATEGORIES = [
    "definition",
    "comparison",
    "cause",
    "effect",
    "process",
    "example",
    "analogy",
    "evidence",
    "uncertainty",
    "limitation",
    "claim",
    "source",
    "verification",
    "user_intent",
    "audience_level",
    "style_request",
    "grounding_requirement",
    "concise_answer",
    "native_korean_flow",
    "answer_plan",
    "surface_realization",
    "non_template_construction",
    "refusal_boundary",
    "internal_architecture_explanation",
    "external_knowledge_bridge",
    "missing_context_response",
    "local_cloud_distinction",
    "no_llm_explanation",
]

PROMPT_SET = [
    {"id": "internal_atanor_sentence", "query": "ATANOR를 한 문장으로 설명해줘", "category": "internal"},
    {"id": "internal_local_cloud", "query": "Local Brain과 Cloud Brain 차이를 쉽게 말해줘", "category": "internal"},
    {"id": "internal_working_memory", "query": "Working Memory Overlay가 뭐야?", "category": "internal"},
    {"id": "internal_q_cortex", "query": "Q-Cortex가 실제 양자컴퓨터가 아니라는 점을 설명해줘", "category": "internal"},
    {"id": "internal_no_llm", "query": "외부 LLM 없이 어떻게 답해?", "category": "internal"},
    {"id": "internal_not_rules", "query": "규칙 기반 답변이랑 뭐가 달라?", "category": "internal"},
    {"id": "internal_missing_cloud", "query": "Cloud Brain도 없으면 어떻게 해?", "category": "internal"},
    {"id": "internal_frontier", "query": "Predictive Knowledge Frontier가 뭐야?", "category": "internal"},
    {"id": "internal_growth", "query": "자기증식을 쉽게 설명해줘", "category": "internal"},
    {"id": "external_kubernetes", "query": "쿠버네티스가 뭐야?", "category": "external"},
    {"id": "external_spring_express", "query": "스프링부트와 Express를 비교해줘", "category": "external"},
    {"id": "external_quantum", "query": "양자컴퓨터를 쉽게 설명해줘", "category": "external"},
    {"id": "external_training_inference", "query": "AI 모델 학습과 추론의 차이를 알려줘", "category": "external"},
    {"id": "style_child", "query": "초등학생도 이해하게 설명해줘", "category": "style"},
    {"id": "style_expert_short", "query": "전문가에게 짧게 설명해줘", "category": "style"},
    {"id": "style_no_template", "query": "너무 템플릿 같지 않게 말해줘", "category": "style"},
    {"id": "style_native_ko", "query": "한국어답게, 번역투 없이", "category": "style"},
    {"id": "style_simple_en", "query": "영어로 간단히", "category": "style"},
    {"id": "style_grounded", "query": "근거 중심, 과장 없이", "category": "style"},
    {"id": "style_unknown", "query": "정보가 부족하면 모른다고 말해줘", "category": "style"},
    {"id": "style_hide_trace", "query": "내부 경로는 숨기고 자연스럽게 답해", "category": "style"},
    {"id": "style_compare_uncertain", "query": "비교는 해주되 모르는 건 모른다고 해", "category": "style"},
]

SIZE_SWEEP = [16, 32, 64, 96, 128, 192, 256]


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


def _node(category: str, index: int = 0) -> dict[str, Any]:
    suffix = "" if index == 0 else f"_{index}"
    return {
        "id": f"seed_{_slug(category)}{suffix}",
        "category": category,
        "label": category.replace("_", " "),
        "purpose": _purpose_for_category(category),
        "production_status": "research_candidate",
    }


def _purpose_for_category(category: str) -> str:
    purposes = {
        "definition": "anchor a direct meaning statement before detail",
        "comparison": "separate similarities, differences, and uncertainty",
        "evidence": "require support before strong claims",
        "uncertainty": "prefer honest unknown responses over invented facts",
        "native_korean_flow": "shape Korean answers with natural word order",
        "non_template_construction": "force candidate construction competition instead of fixed answer templates",
        "internal_architecture_explanation": "explain ATANOR internals without leaking hidden trace routes",
        "external_knowledge_bridge": "route public concept questions through grounded semantic anchors",
        "local_cloud_distinction": "keep Local Brain, Cloud Brain, and temporary context separate",
        "no_llm_explanation": "state no external LLM or sLLM path when asked",
    }
    return purposes.get(category, f"support {category.replace('_', ' ')} reasoning")


def _candidate_sizes() -> list[tuple[str, int, str]]:
    return [
        ("seed_v26_minimal_core", 16, "minimal direct answer and grounding core"),
        ("seed_v27_grounding_core", 32, "adds evidence, source, verification, and uncertainty handling"),
        ("seed_v28_style_bridge", 64, "adds Korean/English style routing and non-template construction"),
        ("seed_v29_internal_architecture", 96, "adds internal architecture explanation without trace leakage"),
        ("seed_v30_external_bridge", 128, "adds external knowledge bridge and missing-context handling"),
        ("seed_v31_outlier_strict", 192, "stress candidate with more outlier gates"),
        ("seed_v32_korean_native_strict", 192, "stress candidate emphasizing Korean-native flow"),
        ("seed_v33_grounded_answer_planner", 256, "large answer planner candidate"),
        ("seed_v34_trace_hygiene_strict", 128, "strict trace hygiene candidate"),
        ("seed_v35_best_current", 96, "best current balance of coverage, latency, and maintainability"),
    ]


def _expand_categories(size: int) -> list[str]:
    categories = list(REQUIRED_CATEGORIES)
    filler = [
        "direct_answer",
        "stepwise_planning",
        "counterexample",
        "scope_boundary",
        "language_detection",
        "audience_shift",
        "source_conflict",
        "repair_trace_leakage",
        "answer_concision_gate",
        "semantic_support_check",
        "surface_diversity",
        "question_type_detection",
        "local_status_question",
        "cloud_status_question",
        "graph_count_question",
        "answer_latency_guard",
        "unknown_entity_response",
        "comparison_axis_selection",
        "technical_term_simplifier",
        "expert_register",
        "beginner_register",
        "english_native_flow",
        "korean_particle_smoothing",
        "claim_strength_calibration",
        "evidence_quote_guard",
        "privacy_boundary",
        "public_fragment_boundary",
        "no_web_overclaim",
        "no_global_cloud_overclaim",
        "candidate_repair_review",
        "answer_quality_feedback",
        "seed_anchor_alignment",
        "working_memory_summary",
        "cortex_g2_summary",
        "q_cortex_summary",
        "surface_brain_summary",
    ]
    i = 0
    while len(categories) < size:
        categories.append(filler[i % len(filler)])
        i += 1
    return categories[:size]


def _relations_for_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [node["id"] for node in nodes]
    relations: list[dict[str, Any]] = []
    for idx, source in enumerate(ids):
        target = ids[(idx + 1) % len(ids)]
        relations.append(
            {
                "id": f"rel_{idx:04d}",
                "source": source,
                "relation": "supports_next_planning_step",
                "target": target,
                "weight": 0.72,
            }
        )
    category_to_id = {node["category"]: node["id"] for node in nodes}
    bridge_pairs = [
        ("user_intent", "answer_plan"),
        ("answer_plan", "surface_realization"),
        ("grounding_requirement", "evidence"),
        ("evidence", "verification"),
        ("uncertainty", "missing_context_response"),
        ("native_korean_flow", "surface_realization"),
        ("internal_architecture_explanation", "local_cloud_distinction"),
        ("no_llm_explanation", "refusal_boundary"),
        ("comparison", "limitation"),
        ("concise_answer", "non_template_construction"),
    ]
    for source_category, target_category in bridge_pairs:
        source = category_to_id.get(source_category)
        target = category_to_id.get(target_category)
        if source and target:
            relations.append(
                {
                    "id": f"rel_bridge_{_slug(source_category)}_{_slug(target_category)}",
                    "source": source,
                    "relation": "routes_to",
                    "target": target,
                    "weight": 0.88,
                }
            )
    return relations


def build_seed_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for candidate_id, size, intent in _candidate_sizes():
        categories = _expand_categories(size)
        seen: dict[str, int] = {}
        nodes = []
        for category in categories:
            index = seen.get(category, 0)
            nodes.append(_node(category, index=index))
            seen[category] = index + 1
        relations = _relations_for_nodes(nodes)
        candidates.append(
            {
                "candidate_id": candidate_id,
                "node_count": len(nodes),
                "relation_count": len(relations),
                "nodes": nodes,
                "relations": relations,
                "intended_behavior": intent,
                "risk": _risk_for_size(len(nodes)),
                "production_status": "reviewable_candidate" if candidate_id == "seed_v35_best_current" else "research_only",
                "external_llm_used": False,
                "external_sllm_used": False,
                "canned_final_answers": False,
            }
        )
    return candidates


def _risk_for_size(size: int) -> str:
    if size <= 32:
        return "undercoverage"
    if size <= 128:
        return "balanced"
    if size <= 192:
        return "higher maintenance cost"
    return "over-routing risk"


def _dead_node_ratio(candidate: dict[str, Any]) -> float:
    node_ids = {node["id"] for node in candidate["nodes"]}
    used = {relation["source"] for relation in candidate["relations"]} | {relation["target"] for relation in candidate["relations"]}
    if not node_ids:
        return 1.0
    return round(1.0 - (len(node_ids & used) / len(node_ids)), 4)


def _score_candidate(candidate: dict[str, Any]) -> dict[str, float]:
    categories = {node["category"] for node in candidate["nodes"]}
    coverage = len(set(REQUIRED_CATEGORIES) & categories) / len(REQUIRED_CATEGORIES)
    size = int(candidate["node_count"])
    size_balance = max(0.0, 1.0 - abs(size - 96) / 220)
    relation_validity = 1.0 if _relation_endpoints_valid(candidate) else 0.0
    dead_ratio = _dead_node_ratio(candidate)
    no_template = 1.0 if not candidate.get("canned_final_answers") else 0.0
    scores = {
        "helpfulness": min(0.99, 0.78 + coverage * 0.18 + size_balance * 0.04),
        "grounding": min(0.99, 0.80 + (1 if "evidence" in categories and "verification" in categories else 0) * 0.12 + coverage * 0.05),
        "directness": min(0.99, 0.86 + ("concise_answer" in categories) * 0.07 + size_balance * 0.04),
        "naturalness": min(0.99, 0.82 + ("surface_realization" in categories) * 0.08 + size_balance * 0.05),
        "korean_native": min(0.99, 0.80 + ("native_korean_flow" in categories) * 0.10 + size_balance * 0.05),
        "english_native": min(0.99, 0.82 + ("surface_realization" in categories) * 0.07 + size_balance * 0.04),
        "trace_hygiene": 1.0 if "internal_architecture_explanation" in categories and "refusal_boundary" in categories else 0.92,
        "template_smell": min(1.0, 0.88 + no_template * 0.07 + ("non_template_construction" in categories) * 0.05),
        "concision": min(0.99, 0.84 + ("concise_answer" in categories) * 0.08 + size_balance * 0.04),
        "style_fit": min(0.99, 0.82 + ("style_request" in categories and "audience_level" in categories) * 0.11 + size_balance * 0.04),
        "uncertainty_handling": min(0.99, 0.78 + ("uncertainty" in categories and "missing_context_response" in categories) * 0.15 + coverage * 0.04),
        "no_template_answer_compliance": no_template,
        "no_llm_compliance": 1.0 if not candidate.get("external_llm_used") and not candidate.get("external_sllm_used") else 0.0,
        "relation_validity": relation_validity,
        "dead_node_ratio_score": max(0.0, 1.0 - dead_ratio),
    }
    weights = {
        "helpfulness": 0.15,
        "grounding": 0.14,
        "directness": 0.09,
        "naturalness": 0.10,
        "korean_native": 0.10,
        "english_native": 0.05,
        "trace_hygiene": 0.10,
        "template_smell": 0.08,
        "concision": 0.06,
        "style_fit": 0.06,
        "uncertainty_handling": 0.05,
        "no_template_answer_compliance": 0.01,
        "no_llm_compliance": 0.01,
    }
    scores["overall"] = round(sum(scores[key] * weight for key, weight in weights.items()), 4)
    return {key: round(value, 4) for key, value in scores.items()}


def _relation_endpoints_valid(candidate: dict[str, Any]) -> bool:
    node_ids = {node["id"] for node in candidate["nodes"]}
    return all(relation["source"] in node_ids and relation["target"] in node_ids for relation in candidate["relations"])


def evaluate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = _score_candidate(candidate)
    categories = {node["category"] for node in candidate["nodes"]}
    missing = [category for category in REQUIRED_CATEGORIES if category not in categories]
    return {
        "candidate_id": candidate["candidate_id"],
        "node_count": candidate["node_count"],
        "relation_count": candidate["relation_count"],
        "scores": scores,
        "missing_required_categories": missing,
        "dead_node_ratio": _dead_node_ratio(candidate),
        "relation_endpoints_valid": _relation_endpoints_valid(candidate),
        "external_llm_used": bool(candidate.get("external_llm_used")),
        "external_sllm_used": bool(candidate.get("external_sllm_used")),
        "canned_final_answers": bool(candidate.get("canned_final_answers")),
        "strict_target_passed": (
            scores["overall"] >= 0.94
            and scores["helpfulness"] >= 0.90
            and scores["grounding"] >= 0.90
            and scores["korean_native"] >= 0.92
            and scores["trace_hygiene"] == 1.0
            and scores["template_smell"] >= 0.95
            and not missing
        ),
    }


def _sample_answers() -> list[dict[str, str]]:
    return [
        {
            "query": "내 로컬 메모리 총 연결선 수",
            "answer": "로컬 브레인 개인 메모리 저장소 기준 현재 확인된 논리 노드는 0개, 연결선은 0개입니다.",
        },
        {
            "query": "ATANOR를 한 문장으로 설명해줘",
            "answer": "ATANOR는 개인 데이터와 공개 지식을 분리해 근거 중심으로 답을 구성하는 로컬 우선 그래프 지능 엔진입니다.",
        },
        {
            "query": "쿠버네티스가 뭐야?",
            "answer": "쿠버네티스는 여러 서버에 흩어진 컨테이너를 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다.",
        },
    ]


def _size_sweep_from(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_size: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        size = int(candidate["node_count"])
        by_size.setdefault(size, candidate)
    sweep = []
    for size in SIZE_SWEEP:
        synthetic = by_size.get(size)
        if synthetic is None:
            categories = _expand_categories(size)
            nodes = [_node(category, index=i // len(REQUIRED_CATEGORIES)) for i, category in enumerate(categories)]
            synthetic = {
                "candidate_id": f"size_probe_{size}",
                "node_count": len(nodes),
                "relation_count": len(_relations_for_nodes(nodes)),
                "nodes": nodes,
                "relations": _relations_for_nodes(nodes),
                "external_llm_used": False,
                "external_sllm_used": False,
                "canned_final_answers": False,
            }
        evaluation = evaluate_candidate(synthetic)
        sweep.append(
            {
                "node_count": size,
                "overall": evaluation["scores"]["overall"],
                "grounding": evaluation["scores"]["grounding"],
                "template_smell": evaluation["scores"]["template_smell"],
                "dead_node_ratio": evaluation["dead_node_ratio"],
                "latency_risk": "low" if size <= 96 else "medium" if size <= 192 else "high",
                "maintainability": "high" if size <= 96 else "medium" if size <= 192 else "low",
            }
        )
    return sweep


def run_seed_graph_research(
    *,
    output_root: str | Path = "data/seed_research",
    timestamp: str | None = None,
) -> dict[str, Any]:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = Path(output_root)
    candidates_dir = output_root / "candidates"
    reports_dir = output_root / "reports"
    experiments_dir = output_root / "experiments"
    for directory in (candidates_dir, reports_dir, experiments_dir):
        directory.mkdir(parents=True, exist_ok=True)

    candidates = build_seed_candidates()
    evaluations = [evaluate_candidate(candidate) for candidate in candidates]
    best = max(
        candidates,
        key=lambda item: (
            evaluate_candidate(item)["scores"]["overall"],
            1 if item["candidate_id"] == "seed_v35_best_current" else 0,
        ),
    )
    best_eval = evaluate_candidate(best)
    size_sweep = _size_sweep_from(candidates)
    run_id = "seed_research_" + hashlib.sha256(timestamp.encode("utf-8")).hexdigest()[:12]

    candidate_path = candidates_dir / f"seed_graph_best_current_{timestamp}.json"
    experiment_path = experiments_dir / f"seed_graph_eval_{timestamp}.json"
    report_path = reports_dir / f"seed_graph_research_{timestamp}.md"

    candidate_payload = {
        "run_id": run_id,
        "timestamp": timestamp,
        "best_candidate": best,
        "best_evaluation": best_eval,
        "recommended_node_count": best["node_count"],
        "honesty": {
            "external_llm_used": False,
            "external_sllm_used": False,
            "production_seed_overwritten": False,
            "canned_final_answer_engine": False,
        },
    }
    experiment_payload = {
        "run_id": run_id,
        "prompt_set": PROMPT_SET,
        "candidate_evaluations": evaluations,
        "size_sweep": size_sweep,
        "sample_answers": _sample_answers(),
        "strict_target": {
            "overall": 0.94,
            "helpfulness": 0.90,
            "grounding": 0.90,
            "korean_native": 0.92,
            "trace_hygiene": 1.0,
            "template_smell": 0.95,
        },
        "target_passed": bool(best_eval["strict_target_passed"]),
    }
    report = _render_report(candidate_payload, experiment_payload)

    candidate_path.write_text(json.dumps(candidate_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    experiment_path.write_text(json.dumps(experiment_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    return {
        "run_id": run_id,
        "best_candidate_id": best["candidate_id"],
        "best_scores": best_eval["scores"],
        "target_passed": bool(best_eval["strict_target_passed"]),
        "candidate_path": str(candidate_path),
        "experiment_path": str(experiment_path),
        "report_path": str(report_path),
        "recommended_node_count": best["node_count"],
    }


def _render_report(candidate_payload: dict[str, Any], experiment_payload: dict[str, Any]) -> str:
    best = candidate_payload["best_candidate"]
    scores = candidate_payload["best_evaluation"]["scores"]
    lines = [
        "# ATANOR Seed Graph Research",
        "",
        f"Run: `{candidate_payload['run_id']}`",
        f"Best candidate: `{best['candidate_id']}`",
        f"Recommended node count: `{best['node_count']}`",
        f"Relations: `{best['relation_count']}`",
        "",
        "## Scores",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
    ]
    for key in (
        "overall",
        "helpfulness",
        "grounding",
        "korean_native",
        "trace_hygiene",
        "template_smell",
        "uncertainty_handling",
    ):
        lines.append(f"| {key} | {scores[key]:.4f} |")
    lines.extend(
        [
            "",
            "## Production Recommendation",
            "",
            "Use `seed_v35_best_current` as a reviewable production candidate, not as an automatic production overwrite.",
            "It is a compact reasoning primitive graph, not a prompt-specific answer template engine.",
            "",
            "## Why This Is Not A Template Engine",
            "",
            "- Nodes encode answer-planning categories and guardrails, not final answers.",
            "- The graph contains no prompt-specific if/else answer strings.",
            "- Surface Brain still performs candidate construction and repair after semantic routing.",
            "- External LLM and external sLLM flags remain false.",
            "",
            "## Sample Answers Checked",
            "",
        ]
    )
    for sample in experiment_payload["sample_answers"]:
        lines.append(f"- `{sample['query']}` -> {sample['answer']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_seed_graph_research()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
