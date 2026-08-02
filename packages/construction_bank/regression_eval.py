from __future__ import annotations

from typing import Any

from .compare import compare_construction_retrieval
from .models import ConstructionBank, INVARIANTS, get_default_construction_bank
from .promotion_gate import DEFAULT_REGRESSION_SET
from .promotion_manifest import ConstructionPromotionManifest, get_manifest


GENERIC_FALLBACK_FRAGMENTS: tuple[str, ...] = (
    "현재 상태를 정리하는 중",
    "다음 요청을 기다리고",
    "바로 반영",
)


def _has_mojibake(text: str) -> bool:
    return any(fragment in text for fragment in ("�", "濡쒖", "?덈", "釉뚮"))


def run_regression_eval(
    *,
    manifest_id: str | None = None,
    manifest: ConstructionPromotionManifest | None = None,
    bank: ConstructionBank | None = None,
) -> dict[str, Any]:
    bank = bank or get_default_construction_bank()
    manifest = manifest or (get_manifest(manifest_id) if manifest_id else None)
    prompts = manifest.regression_set if manifest else DEFAULT_REGRESSION_SET
    rows: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    for prompt in prompts:
        comparison = compare_construction_retrieval(prompt, mode="product", bank=bank)
        answer = str(comparison.get("chosen_answer") or "")
        metadata = comparison.get("metadata", {})
        failures: list[str] = []
        if not answer:
            failures.append("empty_answer")
        if _has_mojibake(answer):
            failures.append("mojibake_answer")
        if any(fragment in answer for fragment in GENERIC_FALLBACK_FRAGMENTS):
            failures.append("irrelevant_generic_fallback")
        if metadata.get("production_active") or metadata.get("production_construction_activation"):
            failures.append("production_activation_detected")
        if metadata.get("external_llm") or metadata.get("external_sllm"):
            failures.append("external_model_detected")
        if failures:
            regressions.append({"prompt": prompt, "failures": failures, "answer": answer})
        rows.append(
            {
                "prompt": prompt,
                "baseline_hand_authored_answer": comparison.get("hand_authored_answer"),
                "self_grown_candidate_answer": comparison.get("self_grown_candidate_answer"),
                "chosen_answer": comparison.get("chosen_answer"),
                "metadata_honesty": {
                    "hand_authored_fallback_used": metadata.get("hand_authored_fallback_used"),
                    "self_grown_construction_used": metadata.get("self_grown_construction_used"),
                    "production_active": metadata.get("production_active"),
                    "production_construction_activation": metadata.get("production_construction_activation"),
                },
                "template_risk": metadata.get("template_risk"),
                "grounding_score": metadata.get("grounding_score"),
                "safety_risk": metadata.get("safety_risk"),
                "failures": failures,
            }
        )
    eligible = list(manifest.candidate_ids) if manifest else []
    return {
        **INVARIANTS,
        "pass": not regressions,
        "regressions": regressions,
        "worst_cases": regressions[:3],
        "eligible_candidate_ids": eligible,
        "manifest_recommendation": "review_ready" if not regressions and eligible else "hold_for_review",
        "rows": rows,
        "production_activation": False,
    }
