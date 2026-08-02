from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Language = Literal["ko", "en"]
AnswerMode = Literal["default", "grounded", "trace", "research"]
GeneratorKind = Literal["baseline", "surface_brain", "repaired_surface_brain"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def honesty_flags() -> dict[str, bool]:
    return {
        "external_llm_judge_used": False,
        "external_llm_generation_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
        "auto_promoted_feedback": False,
        "perfect_factuality_claimed": False,
        "gpt_level_judgment_claimed": False,
    }


@dataclass(slots=True)
class AnswerQualityPrompt:
    prompt_id: str
    category: str
    query: str
    language: Language
    audience_level: str = "beginner"
    tone: str = "clear"
    mode: AnswerMode = "default"
    semantic_context: list[dict[str, Any]] = field(default_factory=list)
    expected_behavior: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerCandidate:
    candidate_id: str
    prompt_id: str
    generator: GeneratorKind
    answer: str
    trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerQualityScore:
    candidate_id: str
    naturalness: float
    helpfulness: float
    directness: float
    trace_hygiene: float
    grounding: float
    template_smell: float
    style_fit: float
    language_native: float
    concision: float
    repair_success: float
    overall: float
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerQualityRun:
    run_id: str
    benchmark_set: str
    total_prompts: int
    average_scores: dict[str, float]
    category_scores: dict[str, dict[str, float]]
    worst_cases: list[dict[str, Any]]
    best_cases: list[dict[str, Any]]
    regressions: list[dict[str, Any]]
    surface_feedback: list[dict[str, Any]]
    honesty: dict[str, bool] = field(default_factory=honesty_flags)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
