from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import ConstructionBank
from packages.construction_bank.promotion_gate import draft_promotion_manifest
from packages.construction_bank.regression_eval import run_regression_eval


def test_regression_eval_flags_generic_fallback(monkeypatch) -> None:
    bank = ConstructionBank()
    candidate = bank.add(
        replace(
            extract_one(
                {
                    "source_type": "operator_example",
                    "language": "ko",
                    "route_type": "voice_status",
                    "act": "voice_question",
                    "text": "Fish 음성 상태는 검증된 런타임 신호가 있을 때만 설명합니다.",
                    "source_refs": ["unit-test"],
                    "grounding_quality": "high",
                }
            ),
            status="reviewed",
        )
    )
    manifest = draft_promotion_manifest(
        bank=bank,
        candidate_ids=(candidate.candidate_id,),
        regression_set=("Fish2 소리 상태 알려줘",),
    )

    def fake_compare(prompt: str, **kwargs):
        return {
            "hand_authored_answer": "fallback",
            "self_grown_candidate_answer": None,
            "chosen_answer": "현재 상태를 정리하는 중입니다.",
            "metadata": {
                "production_active": False,
                "production_construction_activation": False,
                "external_llm": False,
                "external_sllm": False,
            },
        }

    monkeypatch.setattr("packages.construction_bank.regression_eval.compare_construction_retrieval", fake_compare)

    result = run_regression_eval(manifest=manifest, bank=bank)

    assert result["pass"] is False
    assert result["production_activation"] is False
    assert result["eligible_candidate_ids"] == [candidate.candidate_id]
    assert result["regressions"][0]["failures"] == ["irrelevant_generic_fallback"]

