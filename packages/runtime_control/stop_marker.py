from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_STOP_DIR = Path("data") / "audits" / "24h_candidate_run" / "stop_requests"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_run_id(run_id: str) -> str:
    if not run_id or any(part in run_id for part in ("..", "/", "\\")):
        raise ValueError("run_id must be a non-empty path-safe identifier")
    return run_id


@dataclass(frozen=True)
class StopMarker:
    run_id: str
    reason: str
    requested_at: str
    requested_by: str = "user"
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def marker_path(run_id: str, stop_dir: Path | str = DEFAULT_STOP_DIR) -> Path:
    safe_run_id = _require_run_id(run_id)
    return Path(stop_dir) / f"{safe_run_id}.stop.json"


def create_stop_marker(
    run_id: str,
    reason: str,
    *,
    stop_dir: Path | str = DEFAULT_STOP_DIR,
    requested_by: str = "user",
    metadata: dict[str, Any] | None = None,
) -> StopMarker:
    """Create an atomic cooperative stop marker for a standalone runner.

    The marker is a request only. It does not kill a process, mutate stores,
    promote candidates, or imply that finalization has completed.
    """

    if not reason:
        raise ValueError("reason is required")
    marker = StopMarker(_require_run_id(run_id), reason, _utc_now(), requested_by, metadata or {})
    path = marker_path(run_id, stop_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(marker.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return marker


def check_stop_requested(run_id: str, *, stop_dir: Path | str = DEFAULT_STOP_DIR) -> bool:
    """Return true when a cooperative stop marker exists for the run."""

    return marker_path(run_id, stop_dir).exists()


def read_stop_reason(run_id: str, *, stop_dir: Path | str = DEFAULT_STOP_DIR) -> StopMarker | None:
    """Read a cooperative stop marker without mutating it."""

    path = marker_path(run_id, stop_dir)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return StopMarker(
        run_id=str(payload["run_id"]),
        reason=str(payload["reason"]),
        requested_at=str(payload["requested_at"]),
        requested_by=str(payload.get("requested_by") or "user"),
        metadata=dict(payload.get("metadata") or {}),
    )


def clear_stop_marker(run_id: str, *, stop_dir: Path | str = DEFAULT_STOP_DIR) -> bool:
    """Remove a consumed stop marker. Returns true when a marker was removed."""

    path = marker_path(run_id, stop_dir)
    if not path.exists():
        return False
    path.unlink()
    return True
