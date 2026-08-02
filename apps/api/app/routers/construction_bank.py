from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.routers.agentic_micro_os import REVIEW_QUEUE
from packages.construction_bank.compare import compare_construction_retrieval
from packages.construction_bank.extractor import extract_construction_candidates
from packages.construction_bank.models import INVARIANTS, get_default_construction_bank
from packages.construction_bank.promotion_gate import PromotionThresholds, draft_promotion_manifest, promotion_status
from packages.construction_bank.promotion_guard import promotion_requirements
from packages.construction_bank.promotion_manifest import get_manifest, make_rollback_manifest, sign_preview
from packages.construction_bank.proof import run_proof
from packages.construction_bank.regression_eval import run_regression_eval
from packages.construction_bank.retriever import retrieve_constructions
from packages.construction_bank.review_adapter import export_to_review_queue


router = APIRouter(prefix="/api/construction-bank", tags=["construction-bank"])


class ExtractRequest(BaseModel):
    sources: list[dict[str, Any]] = Field(default_factory=list)
    store: bool = True


class RetrieveRequest(BaseModel):
    route_type: str = "open_chat"
    language: str = "ko"
    act: str | None = None
    audience: str = "lab"
    mode: str | None = None
    grounding_context: dict[str, Any] = Field(default_factory=dict)
    recent_output_history: list[str] = Field(default_factory=list)
    limit: int = Field(default=3, ge=1, le=10)


class ExportReviewRequest(BaseModel):
    candidate_id: str


class CompareRequest(BaseModel):
    prompt: str
    mode: str = "lab"
    route_type: str | None = None


class DraftManifestRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    route_scopes: list[str] = Field(default_factory=list)
    language_scopes: list[str] = Field(default_factory=lambda: ["ko"])
    created_by: str = "operator"
    min_naturalness_score: float = 0.62
    min_grounding_score: float = 0.42
    max_template_risk: float = 0.32
    max_safety_risk: float = 0.12


class EvaluateManifestRequest(BaseModel):
    manifest_id: str


class SignPreviewRequest(BaseModel):
    manifest_id: str
    operator_signature: str = ""


class RollbackDraftRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    route_scopes: list[str] = Field(default_factory=list)
    reason: str = "proof_only_rollback_plan"


@router.get("/status")
def construction_bank_status() -> dict[str, Any]:
    bank = get_default_construction_bank()
    return {
        **bank.status(),
        "promotion_guard": promotion_requirements(),
        "review_queue_items_total": REVIEW_QUEUE.status()["items_total"],
    }


@router.get("/promotion/status")
def construction_promotion_status() -> dict[str, Any]:
    return {**INVARIANTS, **promotion_status(get_default_construction_bank())}


@router.get("/candidates")
def construction_bank_candidates(status: str | None = None) -> dict[str, Any]:
    bank = get_default_construction_bank()
    return {
        **INVARIANTS,
        "candidates": [candidate.to_dict() for candidate in bank.list_candidates(status=status)],
    }


@router.post("/extract")
def construction_bank_extract(request: ExtractRequest) -> dict[str, Any]:
    bank = get_default_construction_bank()
    candidates = extract_construction_candidates(request.sources)
    stored = bank.add_many(candidates) if request.store else candidates
    return {
        **INVARIANTS,
        "extracted": len(candidates),
        "stored": len(stored) if request.store else 0,
        "candidates": [candidate.to_dict() for candidate in stored],
    }


@router.post("/retrieve")
def construction_bank_retrieve(request: RetrieveRequest) -> dict[str, Any]:
    return {
        **INVARIANTS,
        **retrieve_constructions(
            route_type=request.route_type,
            language=request.language,
            act=request.act,
            audience=request.audience,
            mode=request.mode,
            grounding_context=request.grounding_context,
            recent_output_history=request.recent_output_history,
            limit=request.limit,
        ),
    }


@router.post("/export-review-item")
def construction_bank_export_review_item(request: ExportReviewRequest) -> dict[str, Any]:
    bank = get_default_construction_bank()
    candidate = bank.candidates.get(request.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="construction candidate not found")
    item = export_to_review_queue(candidate, REVIEW_QUEUE)
    return {
        **INVARIANTS,
        "review_item": item,
        "production_active": False,
        "mutation_performed": False,
    }


@router.post("/compare")
def construction_bank_compare(request: CompareRequest) -> dict[str, Any]:
    return compare_construction_retrieval(
        request.prompt,
        mode=request.mode,
        route_type=request.route_type,
        bank=get_default_construction_bank(),
    )


@router.post("/promotion/manifest/draft")
def construction_promotion_manifest_draft(request: DraftManifestRequest) -> dict[str, Any]:
    route_scopes = tuple(request.route_scopes) if request.route_scopes else ()
    manifest = draft_promotion_manifest(
        bank=get_default_construction_bank(),
        candidate_ids=tuple(request.candidate_ids),
        route_scopes=route_scopes or tuple(sorted({"greeting_smalltalk", "local_cloud_brain_explanation", "limitation_question", "voice_status", "splatra_request", "agentic_os_request"})),
        language_scopes=tuple(request.language_scopes),
        created_by=request.created_by,
        thresholds=PromotionThresholds(
            min_naturalness_score=request.min_naturalness_score,
            min_grounding_score=request.min_grounding_score,
            max_template_risk=request.max_template_risk,
            max_safety_risk=request.max_safety_risk,
        ),
    )
    return {**INVARIANTS, "manifest": manifest.to_dict()}


@router.post("/promotion/manifest/evaluate")
def construction_promotion_manifest_evaluate(request: EvaluateManifestRequest) -> dict[str, Any]:
    manifest = get_manifest(request.manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="construction promotion manifest not found")
    return run_regression_eval(manifest=manifest, bank=get_default_construction_bank())


@router.post("/promotion/manifest/sign-preview")
def construction_promotion_manifest_sign_preview(request: SignPreviewRequest) -> dict[str, Any]:
    if get_manifest(request.manifest_id) is None:
        raise HTTPException(status_code=404, detail="construction promotion manifest not found")
    manifest = sign_preview(request.manifest_id, request.operator_signature)
    return {**INVARIANTS, "manifest": manifest.to_dict(), "production_activation": False}


@router.get("/promotion/manifest/{manifest_id}")
def construction_promotion_manifest_get(manifest_id: str) -> dict[str, Any]:
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="construction promotion manifest not found")
    return {**INVARIANTS, "manifest": manifest.to_dict()}


@router.post("/promotion/rollback/draft")
def construction_promotion_rollback_draft(request: RollbackDraftRequest) -> dict[str, Any]:
    rollback = make_rollback_manifest(
        candidate_ids=tuple(request.candidate_ids),
        route_scopes=tuple(request.route_scopes),
        reason=request.reason,
    )
    return {**INVARIANTS, "rollback": rollback.to_dict(), "production_activation": False}


@router.get("/proof")
def construction_bank_proof() -> dict[str, Any]:
    return run_proof()
