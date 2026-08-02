from __future__ import annotations

from .extractor import extract_construction_candidates
from .models import ConstructionBank, INVARIANTS
from .promotion_guard import promotion_requirements
from .retriever import retrieve_constructions


def run_proof() -> dict[str, object]:
    bank = ConstructionBank()
    candidates = extract_construction_candidates(
        [
            {
                "source_type": "operator_example",
                "language": "ko",
                "route_type": "voice_status",
                "act": "voice_question",
                "text": "Fish 직접 합성은 아직 연결 전이라 Windows 로컬 음성으로 먼저 발화합니다.",
                "source_refs": ["apps/api/app/routers/dual_brain.py"],
                "grounding_quality": "medium",
            }
        ]
    )
    bank.add_many(candidates)
    retrieval = retrieve_constructions(route_type="voice_status", act="voice_question", language="ko", audience="lab", bank=bank)
    return {
        **INVARIANTS,
        "proof": "construction_bank_v0",
        "candidates": len(candidates),
        "retrieved_self_grown_construction": retrieval["retrieved_self_grown_construction"],
        "production_requirements": promotion_requirements(),
        "production_active_count": bank.status()["production_active_count"],
    }
