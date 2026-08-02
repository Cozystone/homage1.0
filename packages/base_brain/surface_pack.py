from __future__ import annotations

import json
from typing import Any

from .models import SURFACE_PATH, SurfaceConstruction, ensure_base_dirs, utc_now_iso


def _construction(
    construction_id: str,
    language: str,
    function: str,
    abstract_shape: str,
    moves: list[str],
    tone: str,
    audience_level: str,
    slots: list[str],
    prior_weight: float,
    group: str,
) -> SurfaceConstruction:
    return SurfaceConstruction(
        construction_id=construction_id,
        language=language,  # type: ignore[arg-type]
        function=function,
        abstract_shape=abstract_shape,
        allowed_discourse_moves=moves,
        tone=tone,
        audience_level=audience_level,  # type: ignore[arg-type]
        slot_types=slots,
        prior_weight=prior_weight,
        avoid_repetition_group=group,
    )


def build_general_surface_pack_v0() -> dict[str, Any]:
    ensure_base_dirs()
    constructions = [
        _construction("direct_definition_ko", "ko", "definition", "X는 Y를 하는 개념입니다.", ["direct_answer", "simple_explanation"], "clear", "beginner", ["concept", "category", "function"], 0.86, "definition"),
        _construction("beginner_analogy_ko", "ko", "analogy", "쉽게 보면 X는 Y에 가깝습니다.", ["beginner_analogy", "example_bridge"], "friendly", "beginner", ["concept", "analogy"], 0.78, "analogy"),
        _construction("contrast_explanation_ko", "ko", "comparison", "A는 ..., B는 ...에 가깝습니다.", ["contrast_frame"], "clear", "intermediate", ["left", "right", "difference"], 0.82, "contrast"),
        _construction("cause_effect_ko", "ko", "cause_effect", "A 때문에 B가 가능해집니다.", ["simple_explanation"], "clear", "intermediate", ["cause", "effect"], 0.74, "causal"),
        _construction("step_by_step_ko", "ko", "process", "먼저 ..., 다음으로 ..., 마지막으로 ...", ["step_by_step"], "precise", "beginner", ["steps"], 0.68, "process"),
        _construction("caveat_soft_ko", "ko", "caveat", "다만 근거가 약한 부분은 조심해서 말해야 합니다.", ["caveat_transition"], "careful", "intermediate", ["caveat"], 0.72, "caveat"),
        _construction("concise_summary_ko", "ko", "summary", "정리하면 핵심은 ...입니다.", ["concise_summary"], "compact", "beginner", ["summary"], 0.76, "summary"),
        _construction("expert_explanation_ko", "ko", "expert_detail", "기술적으로는 A가 B와 C를 조율하는 구조입니다.", ["expert_detail"], "technical", "expert", ["mechanism", "constraints"], 0.66, "expert"),
        _construction("direct_definition_en", "en", "definition", "X is a system that does Y.", ["direct_answer", "simple_explanation"], "clear", "beginner", ["concept", "category", "function"], 0.86, "definition"),
        _construction("beginner_analogy_en", "en", "analogy", "In simple terms, X works like Y.", ["beginner_analogy", "example_bridge"], "friendly", "beginner", ["concept", "analogy"], 0.78, "analogy"),
        _construction("contrast_explanation_en", "en", "comparison", "A focuses on ..., while B focuses on ....", ["contrast_frame"], "clear", "intermediate", ["left", "right", "difference"], 0.82, "contrast"),
        _construction("cause_effect_en", "en", "cause_effect", "Because A is true, B becomes possible.", ["simple_explanation"], "clear", "intermediate", ["cause", "effect"], 0.74, "causal"),
        _construction("step_by_step_en", "en", "process", "First ..., then ..., finally ....", ["step_by_step"], "precise", "beginner", ["steps"], 0.68, "process"),
        _construction("caveat_soft_en", "en", "caveat", "One caveat is that unsupported claims should be qualified.", ["caveat_transition"], "careful", "intermediate", ["caveat"], 0.72, "caveat"),
        _construction("concise_summary_en", "en", "summary", "In short, the key point is ....", ["concise_summary"], "compact", "beginner", ["summary"], 0.76, "summary"),
        _construction("expert_explanation_en", "en", "expert_detail", "Technically, A coordinates B under constraints C.", ["expert_detail"], "technical", "expert", ["mechanism", "constraints"], 0.66, "expert"),
    ]
    pack = {
        "pack_id": "general_surface_v0",
        "version": "0.1.2",
        "created_at": utc_now_iso(),
        "constructions": [construction.to_dict() for construction in constructions],
        "notes": [
            "Construction entries are candidates for selection and composition.",
            "They are not fixed final answer templates.",
        ],
        "honesty": {
            "external_llm_used": False,
            "trained_decoder_used": False,
            "rigid_if_intent_return_template": False,
        },
    }
    SURFACE_PATH.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return pack
