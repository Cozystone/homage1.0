from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .models import Observation


class Sensor(Protocol):
    name: str

    def observe(self, context: dict[str, Any]) -> Observation:
        ...


def _obs(sensor: str, status: str, summary: str, severity: str = "info", payload: dict[str, Any] | None = None) -> Observation:
    return Observation(
        observation_id=f"obs-{sensor}",
        sensor=sensor,
        status=status,
        summary=summary,
        severity=severity,  # type: ignore[arg-type]
        payload=payload or {},
        source_refs=[f"context:{sensor}"],
        read_only=True,
    )


class GitWorktreeSensor:
    name = "git_worktree"

    def observe(self, context: dict[str, Any]) -> Observation:
        dirty = bool(context.get("git_dirty", context.get("dirty_worktree", False)))
        count = int(context.get("dirty_files", 0) or 0)
        if dirty or count:
            return _obs(self.name, "dirty", f"Dirty worktree detected ({count} tracked/untracked hints).", "warning", {"dirty": True, "count": count})
        return _obs(self.name, "clean", "No dirty worktree signal in lifecycle context.", "info", {"dirty": False})


class DirtyWorktreeSensor(GitWorktreeSensor):
    name = "dirty_worktree"


class CandidateBacklogSensor:
    name = "candidate_backlog"

    def observe(self, context: dict[str, Any]) -> Observation:
        backlog = int(context.get("candidate_backlog", 0) or 0)
        if backlog > 0:
            return _obs(self.name, "attention", f"{backlog} candidate items need review.", "notice", {"count": backlog})
        return _obs(self.name, "empty", "No candidate backlog signal.", "info", {"count": 0})


class PromotionReviewSensor:
    name = "promotion_review"

    def observe(self, context: dict[str, Any]) -> Observation:
        count = int(context.get("promotion_review_backlog", 0) or 0)
        if count:
            return _obs(self.name, "attention", f"{count} promotion review items are waiting.", "notice", {"count": count})
        return _obs(self.name, "empty", "No promotion review backlog signal.", "info", {"count": 0})


class MemoryApprovalSensor:
    name = "memory_approval"

    def observe(self, context: dict[str, Any]) -> Observation:
        count = int(context.get("memory_review_backlog", 0) or 0)
        if count:
            return _obs(self.name, "attention", f"{count} memory candidates require approval.", "notice", {"count": count})
        return _obs(self.name, "empty", "No memory approval backlog signal.", "info", {"count": 0})


class SelfhoodRuntimeSensor:
    name = "selfhood_runtime"

    def observe(self, context: dict[str, Any]) -> Observation:
        state = str(context.get("selfhood_state", "idle"))
        return _obs(self.name, state, f"Selfhood runtime observed as {state}.", "info", {"state": state})


class VoiceReadinessSensor:
    name = "voice_readiness"

    def observe(self, context: dict[str, Any]) -> Observation:
        available = bool(context.get("voice_available", False))
        status = "available" if available else "optional_unavailable"
        summary = "Voice path is available but optional; text remains primary." if available else "Voice path is optional and not required."
        return _obs(self.name, status, summary, "notice" if available else "info", {"voice_available": available, "always_listening": False})


class LogicalSphereSensor:
    name = "logical_sphere"

    def observe(self, context: dict[str, Any]) -> Observation:
        score = context.get("logical_sphere_score")
        if score is None:
            return _obs(self.name, "unknown", "Logical Sphere status was not supplied.", "info")
        return _obs(self.name, "observed", f"Logical Sphere score observed: {score}.", "info", {"score": score})


class DiskResourceSensor:
    name = "disk_resource"

    def observe(self, context: dict[str, Any]) -> Observation:
        free_gib = context.get("disk_free_gib")
        if free_gib is None:
            return _obs(self.name, "unknown", "Disk free space was not supplied.", "info")
        value = float(free_gib)
        if value < 40.0:
            return _obs(self.name, "low", f"Disk free space is below long-run guard: {value:.2f} GiB.", "warning", {"free_gib": value})
        return _obs(self.name, "ok", f"Disk free space is healthy: {value:.2f} GiB.", "info", {"free_gib": value})


def default_sensors() -> list[Sensor]:
    return [
        GitWorktreeSensor(),
        CandidateBacklogSensor(),
        PromotionReviewSensor(),
        MemoryApprovalSensor(),
        SelfhoodRuntimeSensor(),
        VoiceReadinessSensor(),
        LogicalSphereSensor(),
        DiskResourceSensor(),
        DirtyWorktreeSensor(),
    ]


def observe_all(context: dict[str, Any], sensors: list[Sensor] | None = None) -> list[Observation]:
    repo_root = context.get("repo_root")
    if repo_root is not None:
        Path(repo_root)
    observations: list[Observation] = []
    for sensor in sensors or default_sensors():
        try:
            observations.append(sensor.observe(context))
        except Exception as exc:  # pragma: no cover - defensive read-only fallback
            observations.append(_obs(sensor.name, "unavailable", f"{sensor.name} unavailable: {exc}", "warning"))
    return observations
