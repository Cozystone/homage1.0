from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from datagate import DataGateConfig, PipelineRunner
from pydantic import BaseModel, Field


RunStateName = Literal["idle", "running", "completed", "failed"]


class DataGateRunRequest(BaseModel):
    input_dir: str = "data/raw"
    min_chars: int = Field(default=200, ge=0)
    max_special_char_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    max_link_density: float = Field(default=0.40, ge=0.0, le=1.0)


class DataGateRunAccepted(BaseModel):
    run_id: str
    state: Literal["running"]


class DataGateStatus(BaseModel):
    state: RunStateName
    run_id: str | None = None
    total: int = 0
    accepted: int = 0
    rejected: int = 0
    rejection_breakdown: dict[str, int] = {}
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class DataGateRunAlreadyRunning(RuntimeError):
    """Raised when a new run is requested while one is already running."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id() -> str:
    return "dg-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _data_root_for(input_dir: str) -> Path:
    input_path = Path(input_dir)
    return input_path.parent if input_path.name == "raw" else Path("data")


def _config_from_request(request: DataGateRunRequest) -> DataGateConfig:
    data_root = _data_root_for(request.input_dir)
    Path(request.input_dir).mkdir(parents=True, exist_ok=True)
    return DataGateConfig(
        input_dir=request.input_dir,
        cleaned_dir=str(data_root / "cleaned"),
        rejected_dir=str(data_root / "rejected"),
        metadata_dir=str(data_root / "metadata"),
        min_chars=request.min_chars,
        max_special_char_ratio=request.max_special_char_ratio,
        max_link_density=request.max_link_density,
    )


class DataGateService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = DataGateStatus(state="idle")

    def reset_for_tests(self) -> None:
        with self._lock:
            self._status = DataGateStatus(state="idle")

    def status(self) -> DataGateStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def start_run(self, request: DataGateRunRequest) -> DataGateRunAccepted:
        config = _config_from_request(request)
        run_id = _make_run_id()
        started_at = _utc_now_iso()
        with self._lock:
            if self._status.state == "running":
                raise DataGateRunAlreadyRunning("DataGate run already in progress")
            self._status = DataGateStatus(
                state="running",
                run_id=run_id,
                started_at=started_at,
            )
        self._pending_config = config
        return DataGateRunAccepted(run_id=run_id, state="running")

    def run_pending(self) -> None:
        config = self._pending_config
        try:
            report = PipelineRunner(config).run()
            with self._lock:
                self._status = DataGateStatus(
                    state=report.state,
                    run_id=report.run_id,
                    total=report.total,
                    accepted=report.accepted,
                    rejected=report.rejected,
                    rejection_breakdown=report.rejection_breakdown,
                    started_at=report.started_at,
                    finished_at=report.finished_at,
                    error=report.error,
                )
        except Exception as exc:  # pragma: no cover - defensive integration guard
            with self._lock:
                previous = self._status
                self._status = DataGateStatus(
                    state="failed",
                    run_id=previous.run_id,
                    started_at=previous.started_at,
                    finished_at=_utc_now_iso(),
                    error=str(exc),
                )


datagate_service = DataGateService()
