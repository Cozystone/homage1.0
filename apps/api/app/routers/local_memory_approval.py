from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.local_memory_approval import service


router = APIRouter(prefix="/api/local-memory-approval", tags=["local-memory-approval"])

SourceTypeRequest = Literal[
    "user_text",
    "voice_transcript",
    "selfhood_runtime_proposal",
    "morning_brief",
    "project_fact",
    "preference",
    "correction",
]


class SessionRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    source_type: SourceTypeRequest = "user_text"


class DecisionRequest(BaseModel):
    candidate_id: str
    decision: str
    edited_summary: str | None = None
    notes: str | None = None
    reviewer: str = "user"


@router.get("/status")
def status() -> dict:
    return service.get_status()


@router.post("/session")
def create_session(request: SessionRequest) -> dict:
    try:
        return service.create_session_from_texts(request.texts, request.source_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions")
def sessions() -> dict:
    return {
        "sessions": service.list_sessions(),
        "safety": service.safety_invariants(),
        "apply_enabled": False,
        "local_brain_write": False,
    }


@router.get("/sessions/{session_id}")
def session_detail(session_id: str) -> dict:
    try:
        return service.get_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory approval session: {session_id}") from exc


@router.post("/sessions/{session_id}/decision")
def decide(session_id: str, request: DecisionRequest) -> dict:
    try:
        return service.add_decision(
            session_id,
            request.candidate_id,
            request.decision,
            edited_summary=request.edited_summary,
            notes=request.notes,
            reviewer=request.reviewer,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory approval session: {session_id}") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/manifest-draft")
def manifest_draft(session_id: str) -> dict:
    try:
        return service.build_manifest_draft(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory approval session: {session_id}") from exc
