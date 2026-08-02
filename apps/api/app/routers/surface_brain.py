from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from packages.agentic_micro_os.permission_gate import PermissionScope
from packages.surface_brain.extraction import extract_surface_projection
from packages.surface_brain.audit_log import list_repair_audit_events
from packages.surface_brain.feedback_adapter import convert_feedback_and_enqueue_candidates
from packages.surface_brain.models import SourceSentence, honesty_flags
from packages.surface_brain.monitor import repair_answer_for_mode
from packages.surface_brain.proof import run_surface_brain_proof
from packages.surface_brain.realization_planner import plan_speech, realize_answer
from packages.surface_brain.review_queue import (
    approve_repair_candidate,
    edit_repair_candidate,
    get_repair_candidate,
    list_repair_candidates,
    reject_repair_candidate,
)
from packages.surface_brain.rule_registry import disable_rule, enable_rule, load_production_rules, rollback_rule
from packages.surface_brain.storage import SURFACE_ROOT, read_jsonl


router = APIRouter(tags=["surface-brain"])


class SourceSentenceRequest(BaseModel):
    source_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    url: str | None = None
    title: str | None = None
    license: str = "unknown"
    usage_allowed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechPlanRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    semantic_context: dict[str, Any] = Field(default_factory=dict)
    language: str | None = None
    audience_level: str = "beginner"
    tone: str = "clear"
    mode: str = "default"


class SpeechRealizeRequest(BaseModel):
    surface_plan: dict[str, Any] = Field(default_factory=dict)
    semantic_context: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    decoder_mode: str = "deterministic"


class RepairAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    mode: str = "default"
    trace: dict[str, Any] = Field(default_factory=dict)


class FeedbackToRepairCandidatesRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    feedback_items: list[dict[str, Any]] = Field(default_factory=list)


class ReviewDecisionRequest(BaseModel):
    reviewer: str = "local_operator"
    comment: str | None = None


class RepairCandidateEditRequest(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


def _bound_operator(
    scope: PermissionScope,
    token: str | None,
    *,
    action: str,
) -> str:
    # Reuse the one process-owned operator boundary.  Importing the module here
    # preserves its singleton and lets API/bootstrap tests replace it without a
    # second authority object.
    from app.routers import agentic_micro_os

    authorization = agentic_micro_os.PERMISSION_GATE.verify_bound_operator_action(
        scope,
        signed_token=token,
        action=action,
    )
    if not authorization.get("allowed"):
        raise HTTPException(
            status_code=403,
            detail={
                "reason": authorization.get("reason")
                or "server_bound_operator_required",
                "required_boundary": "agentic_micro_os_permission_gate",
                "required_scope": scope.value,
            },
        )
    operator_id = authorization.get("bound_operator_id")
    if not isinstance(operator_id, str) or not operator_id:
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "server_bound_operator_identity_missing",
                "required_boundary": "agentic_micro_os_permission_gate",
                "required_scope": scope.value,
            },
        )
    return operator_id


def _require_review_operator(
    token: str | None = Header(
        default=None,
        alias="X-Atanor-Operator-Delegation",
    ),
) -> str:
    return _bound_operator(
        PermissionScope.REVIEW_DRAFT_WRITE,
        token,
        action="surface_brain.review_mutation",
    )


def _require_production_operator(
    token: str | None = Header(
        default=None,
        alias="X-Atanor-Operator-Delegation",
    ),
) -> str:
    return _bound_operator(
        PermissionScope.CLOUD_PRODUCTION_WRITE,
        token,
        action="surface_brain.production_mutation",
    )


def _flags() -> dict[str, Any]:
    return {**honesty_flags(), "final_answer_generation_claimed": True}


def _public_input_trust() -> dict[str, Any]:
    """Receipt for data crossing the unauthenticated public speech boundary."""

    return {
        "boundary": "public_api",
        "authority": "untrusted",
        "tainted": True,
    }


def _public_surface_context(context: dict[str, Any]) -> dict[str, Any]:
    """Keep lexical hints while stripping every caller-minted truth signal.

    Public callers may help choose words, but their evidence, relations, claims,
    confidence, coverage, and status fields are not an authority source.
    """

    candidate = context.get("result") if isinstance(context.get("result"), dict) else context
    concepts: list[str] = []
    seen: set[str] = set()
    raw_items = [
        *(candidate.get("concepts") or []),
        *(candidate.get("active_concepts") or []),
        *(candidate.get("matched_nodes") or []),
    ]
    for item in raw_items:
        value: Any = item
        if isinstance(item, dict):
            value = (
                item.get("label")
                or item.get("primary_name")
                or item.get("canonical_name")
                or item.get("name")
            )
        text = str(value or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        concepts.append(text[:200])
        seen.add(key)
        if len(concepts) >= 32:
            break
    return {"concepts": concepts}


def _public_plan_language(surface_plan: dict[str, Any]) -> str | None:
    language = str(surface_plan.get("language") or "").strip().lower()
    return language if language in {"ko", "en"} else None


@router.get("/api/surface-brain/status")
def surface_brain_status() -> dict[str, Any]:
    root = Path(SURFACE_ROOT)
    plans = read_jsonl(root / "traces" / "surface_plans.jsonl", limit=1000)
    answers = read_jsonl(root / "traces" / "realized_answers.jsonl", limit=1000)
    return {
        "state": "active",
        "architecture": "Surface Brain",
        "semantic_surface_split": True,
        "construction_competition": True,
        "q_cortex_optional": True,
        "plans": len(plans),
        "answers": len(answers),
        "trace_hidden_by_default": True,
        **_flags(),
    }


@router.post("/api/surface-brain/extract")
def surface_brain_extract(request: SourceSentenceRequest) -> dict[str, Any]:
    source = SourceSentence.from_text(
        request.text,
        source_id=request.source_id,
        url=request.url,
        title=request.title,
        license=request.license,
        usage_allowed=request.usage_allowed,
        metadata=request.metadata,
    )
    return {"surface_projection": extract_surface_projection(source), "source_hash": source.source_hash, "stored_raw_text": False, **_flags()}


@router.post("/api/speech/plan")
def speech_plan(request: SpeechPlanRequest) -> dict[str, Any]:
    return {
        **plan_speech(
            request.query,
            _public_surface_context(request.semantic_context),
            language=request.language,
            audience_level=request.audience_level,
            tone=request.tone,
            mode=request.mode,
            input_trust=_public_input_trust(),
        ),
        **_flags(),
    }


@router.post("/api/speech/realize")
def speech_realize(request: SpeechRealizeRequest) -> dict[str, Any]:
    # A public surface plan is presentation input, not a proof that a prior plan
    # was server-generated. Rebuild it from the query and lexical-only context,
    # then realize without caller-supplied semantic facts.
    public_context = _public_surface_context(request.semantic_context)
    plan = plan_speech(
        request.query,
        public_context,
        language=_public_plan_language(request.surface_plan),
        input_trust=_public_input_trust(),
    )
    return {
        **realize_answer(
            plan,
            {},
            query=request.query,
            decoder_mode=request.decoder_mode,
            input_trust=_public_input_trust(),
        ),
        **_flags(),
    }


@router.post("/api/surface-brain/repair-answer")
def surface_brain_repair_answer(request: RepairAnswerRequest) -> dict[str, Any]:
    result = repair_answer_for_mode(request.answer, mode=request.mode, trace=request.trace)
    return {**result, **_flags()}


@router.post("/api/surface-brain/feedback-to-repair-candidates")
def surface_brain_feedback_to_repair_candidates(request: FeedbackToRepairCandidatesRequest) -> dict[str, Any]:
    return {
        **convert_feedback_and_enqueue_candidates(request.feedback_items, request.run_id),
        **_flags(),
    }


@router.get("/api/surface-brain/repair-candidates")
def surface_brain_repair_candidates(status: str | None = None) -> dict[str, Any]:
    rows = list_repair_candidates(status=status)
    return {"candidates": rows, "count": len(rows), "review_required": True, **_flags()}


@router.get("/api/surface-brain/repair-candidates/{candidate_id}")
def surface_brain_repair_candidate_detail(candidate_id: str) -> dict[str, Any]:
    return {**get_repair_candidate(candidate_id), **_flags()}


@router.post("/api/surface-brain/repair-candidates/{candidate_id}/approve")
def surface_brain_approve_repair_candidate(
    candidate_id: str,
    request: ReviewDecisionRequest,
    operator_id: str = Depends(_require_production_operator),
) -> dict[str, Any]:
    return {
        "production_rule": approve_repair_candidate(
            candidate_id,
            reviewer=operator_id,
            comment=request.comment,
        ),
        **_flags(),
    }


@router.post("/api/surface-brain/repair-candidates/{candidate_id}/reject")
def surface_brain_reject_repair_candidate(
    candidate_id: str,
    request: ReviewDecisionRequest,
    operator_id: str = Depends(_require_review_operator),
) -> dict[str, Any]:
    return {
        "candidate": reject_repair_candidate(
            candidate_id,
            reviewer=operator_id,
            comment=request.comment,
        ),
        **_flags(),
    }


@router.post("/api/surface-brain/repair-candidates/{candidate_id}/edit")
def surface_brain_edit_repair_candidate(
    candidate_id: str,
    request: RepairCandidateEditRequest,
    operator_id: str = Depends(_require_review_operator),
) -> dict[str, Any]:
    return {
        "candidate": edit_repair_candidate(
            candidate_id,
            request.patch,
            editor=operator_id,
        ),
        **_flags(),
    }


@router.get("/api/surface-brain/production-rules")
def surface_brain_production_rules() -> dict[str, Any]:
    rows = load_production_rules()
    return {"production_rules": rows, "count": len(rows), **_flags()}


@router.post("/api/surface-brain/production-rules/{rule_id}/enable")
def surface_brain_enable_production_rule(
    rule_id: str,
    operator_id: str = Depends(_require_production_operator),
) -> dict[str, Any]:
    return {
        "production_rule": enable_rule(rule_id, actor=operator_id),
        **_flags(),
    }


@router.post("/api/surface-brain/production-rules/{rule_id}/disable")
def surface_brain_disable_production_rule(
    rule_id: str,
    operator_id: str = Depends(_require_production_operator),
) -> dict[str, Any]:
    return {
        "production_rule": disable_rule(rule_id, actor=operator_id),
        **_flags(),
    }


@router.post("/api/surface-brain/production-rules/{rule_id}/rollback")
def surface_brain_rollback_production_rule(
    rule_id: str,
    operator_id: str = Depends(_require_production_operator),
) -> dict[str, Any]:
    return {
        "rollback": rollback_rule(rule_id, actor=operator_id),
        **_flags(),
    }


@router.get("/api/surface-brain/repair-audit")
def surface_brain_repair_audit(limit: int = 100) -> dict[str, Any]:
    rows = list_repair_audit_events(limit=limit)
    return {"events": rows, "count": len(rows), **_flags()}


@router.post("/api/surface-brain/proof")
def surface_brain_proof() -> dict[str, Any]:
    return {**run_surface_brain_proof(), **_flags()}
