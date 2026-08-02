from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.contribution_service import (
    ContributionValidationError,
    TaskResult,
    default_contribution_service,
)


router = APIRouter(prefix="/api/contribution", tags=["contribution"])


class ContributionSettingsRequest(BaseModel):
    cpu_limit_percent: int | None = None
    gpu_enabled: bool | None = None
    gpu_limit_percent: int | None = None
    ram_limit_gb: float | None = None
    battery_pause: bool | None = None
    thermal_pause: bool | None = None
    night_only: bool | None = None


class TaskResultRequest(BaseModel):
    task_id: str
    status: str
    result_payload: dict[str, Any] = Field(default_factory=dict)
    runtime_ms: int = Field(default=1, ge=1)
    memory_peak_mb: int = Field(default=0, ge=0)
    checksum: str = ""
    error_message: str | None = None
    local_trace_id: str | None = None


@router.get("/status")
def contribution_status() -> dict[str, Any]:
    return default_contribution_service.get_status()


@router.post("/settings")
def update_contribution_settings(payload: ContributionSettingsRequest) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(exclude_none=True)
    else:
        data = payload.dict(exclude_none=True)
    return default_contribution_service.update_settings(data)


@router.post("/register")
def register_contributor() -> dict[str, Any]:
    return default_contribution_service.register()


@router.post("/heartbeat")
def contribution_heartbeat() -> dict[str, Any]:
    return default_contribution_service.heartbeat()


@router.post("/poll")
def poll_public_task() -> dict[str, Any]:
    try:
        return default_contribution_service.poll_public_task()
    except ContributionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/run-once")
def run_public_task_once() -> dict[str, Any]:
    return default_contribution_service.run_current_task()


@router.post("/submit")
def submit_public_task_result(payload: TaskResultRequest) -> dict[str, Any]:
    if payload.status not in {"completed", "rejected", "failed", "timed_out"}:
        raise HTTPException(status_code=422, detail="invalid task status")
    result = TaskResult(
        task_id=payload.task_id,
        node_id=default_contribution_service.node.node_id,
        status=payload.status,  # type: ignore[arg-type]
        result_payload=payload.result_payload,
        runtime_ms=payload.runtime_ms,
        memory_peak_mb=payload.memory_peak_mb,
        checksum=payload.checksum,
        submitted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        error_message=payload.error_message,
        local_trace_id=payload.local_trace_id,
    )
    return default_contribution_service.submit_task_result(result)


@router.post("/pause")
def pause_contributor() -> dict[str, Any]:
    return default_contribution_service.pause()


@router.post("/resume")
def resume_contributor() -> dict[str, Any]:
    return default_contribution_service.resume()


@router.post("/disable")
def disable_contributor() -> dict[str, Any]:
    return default_contribution_service.disable()


@router.get("/credits")
def contribution_credits() -> dict[str, Any]:
    return default_contribution_service.list_credits()


@router.get("/tasks/recent")
def contribution_recent_tasks() -> dict[str, Any]:
    return default_contribution_service.list_recent_tasks()
