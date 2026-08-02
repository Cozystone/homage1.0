from pydantic import BaseModel
from fastapi import APIRouter

from app.services.alpha_services import alpha_service

router = APIRouter(prefix="/api/guard", tags=["guard"])


class GuardCheckRequest(BaseModel):
    draft_answer: str
    evidence_bundle: dict | None = None


@router.post("/check")
def check_guard(request: GuardCheckRequest) -> dict:
    return alpha_service.check_guard(request.draft_answer, request.evidence_bundle)


@router.get("/status")
def guard_status() -> dict:
    return alpha_service.guard_status()
