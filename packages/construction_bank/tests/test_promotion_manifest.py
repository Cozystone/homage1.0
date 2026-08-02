from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import ConstructionBank
from packages.construction_bank.promotion_gate import draft_promotion_manifest
from packages.construction_bank.promotion_manifest import get_rollback, sign_preview


def _candidate(status: str = "candidate"):
    base = extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 선택 기능이고, 준비되지 않으면 텍스트 대화로 이어갑니다.",
            "source_refs": ["unit-test"],
            "grounding_quality": "high",
        }
    )
    return replace(base, status=status) if status != "candidate" else base


def test_raw_candidate_is_not_manifest_eligible() -> None:
    bank = ConstructionBank()
    raw = bank.add(_candidate())

    manifest = draft_promotion_manifest(bank=bank, candidate_ids=(raw.candidate_id,))

    assert manifest.candidate_ids == ()
    assert manifest.status == "draft"
    assert manifest.production_activation is False
    assert manifest.to_dict()["production_construction_activation"] is False
    assert manifest.entries[0].activation_allowed is False
    assert "raw_candidate_not_promotable" in manifest.entries[0].rejection_reasons


def test_reviewed_candidate_creates_review_ready_manifest_and_rollback_plan() -> None:
    bank = ConstructionBank()
    reviewed = bank.add(_candidate(status="reviewed"))

    manifest = draft_promotion_manifest(bank=bank, candidate_ids=(reviewed.candidate_id,))
    rollback = get_rollback(manifest.rollback_manifest_id)

    assert manifest.status == "review_ready"
    assert manifest.candidate_ids == (reviewed.candidate_id,)
    assert manifest.entries[0].rejection_reasons == ()
    assert manifest.entries[0].activation_allowed is False
    assert manifest.to_dict()["signed_manifest_required"] is True
    assert manifest.to_dict()["rollback_required"] is True
    assert rollback is not None
    assert rollback.executable is False
    assert rollback.candidate_ids_to_disable == (reviewed.candidate_id,)


def test_sign_preview_never_turns_on_production_activation() -> None:
    bank = ConstructionBank()
    reviewed = bank.add(_candidate(status="reviewed"))
    manifest = draft_promotion_manifest(bank=bank, candidate_ids=(reviewed.candidate_id,))

    signed = sign_preview(manifest.manifest_id, "operator-preview")

    assert signed.status == "signed"
    assert signed.operator_signature == "operator-preview"
    assert signed.production_activation is False
    assert signed.to_dict()["production_active"] is False
    assert signed.to_dict()["proof_only"] is True

