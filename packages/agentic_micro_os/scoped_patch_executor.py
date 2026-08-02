from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import difflib
import hashlib
import uuid
from typing import Any

from packages.agentic_micro_os.permission_gate import AutonomyTier, PermissionGate, PermissionScope


APPLY_CONFIRMATION = "APPLY SCOPED PATCH"
ROLLBACK_CONFIRMATION = "ROLLBACK SCOPED PATCH"
DEFAULT_MAX_FILE_BYTES = 512 * 1024
DEFAULT_MAX_DIFF_LINES = 300
TEXT_SUFFIXES = {".css", ".md", ".py", ".ts", ".tsx", ".txt"}
FORBIDDEN_PARTS = {
    ".env",
    "candidate_store",
    "candidate_stores",
    "local_brain",
    "verified_store_v0",
}


@dataclass(frozen=True)
class ScopedPatchRequest:
    target_path: str
    expected_old_text: str
    replacement_text: str
    reason: str
    operator_confirmation: str = ""
    tier_session_id: str = ""
    required_subswitches: list[str] = field(default_factory=lambda: ["full_file_write"])
    dry_run: bool = True
    operator_id: str = "operator"


@dataclass
class ScopedPatchPlan:
    plan_id: str
    target_path: str
    allowed: bool
    denied_reason: str = ""
    diff_preview: str = ""
    backup_path: str = ""
    rollback_patch: str = ""
    risk_level: str = "medium"
    requires_tier4: bool = True
    requires_full_file_write: bool = True
    requires_typed_confirmation: bool = True
    mutation_performed: bool = False
    audit_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScopedPatchResult:
    plan_id: str
    applied: bool
    mutation_performed: bool
    backup_path: str = ""
    rollback_patch: str = ""
    audit_event_id: str = ""
    denied_reason: str = ""
    diff_summary: str = ""
    target_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScopedPatchRollbackRequest:
    target_path: str
    backup_path: str
    operator_confirmation: str = ""
    tier_session_id: str = ""
    operator_id: str = "operator"


@dataclass
class ScopedPatchExecutor:
    gate: PermissionGate
    project_root: Path
    backup_dir: Path | None = None
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_diff_lines: int = DEFAULT_MAX_DIFF_LINES

    def __post_init__(self) -> None:
        if self.backup_dir is None:
            object.__setattr__(self, "backup_dir", self.project_root / "runtime" / "agentic_micro_os" / "scoped_patch_backups")

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "host_executor_v1_scoped_only": True,
            "apply_confirmation": APPLY_CONFIRMATION,
            "rollback_confirmation": ROLLBACK_CONFIRMATION,
            "max_file_bytes": self.max_file_bytes,
            "max_diff_lines": self.max_diff_lines,
            "allowed_path_classes": [
                "apps/web/app/*.tsx",
                "apps/web/app/*.css",
                "apps/api/app/routers/*.py",
                "packages/agentic_micro_os/*.py",
                "packages/splatra_turbovec/*.py",
                "docs/*.md",
            ],
            "rejected_path_classes": [
                "data/**",
                "runtime/**",
                "external_repos/**",
                "Local Brain stores",
                "verified_store_v0",
                "candidate stores",
                ".env files",
                "secrets",
                "binary files",
                "lockfiles",
            ],
            "permission_gate": self.gate.status(),
        }

    def plan(self, request: ScopedPatchRequest) -> ScopedPatchPlan:
        plan_id = f"scoped_patch_{uuid.uuid4().hex[:16]}"
        resolved, denied = self._validate_target_path(request.target_path)
        if denied:
            return self._denied_plan(plan_id, request.target_path, denied, request.operator_id)
        assert resolved is not None
        original, denied = self._read_text_target(resolved)
        if denied:
            return self._denied_plan(plan_id, str(resolved), denied, request.operator_id)
        assert original is not None
        if not request.expected_old_text:
            return self._denied_plan(plan_id, str(resolved), "expected_old_text is required", request.operator_id)
        if request.expected_old_text not in original:
            return self._denied_plan(plan_id, str(resolved), "expected_old_text not found", request.operator_id)
        updated = original.replace(request.expected_old_text, request.replacement_text, 1)
        diff_preview = _unified_diff(original, updated, resolved)
        diff_lines = diff_preview.splitlines()
        if len(diff_lines) > self.max_diff_lines:
            return self._denied_plan(plan_id, str(resolved), f"diff exceeds {self.max_diff_lines} lines", request.operator_id)
        rollback_patch = _unified_diff(updated, original, resolved, from_label="patched", to_label="rollback")
        record = self.gate.audit_log.append("scoped_patch_plan", {
            "allowed": True,
            "target_path": str(resolved),
            "operator_id": request.operator_id,
            "reason": request.reason,
            "dry_run": request.dry_run,
            "mutation_performed": False,
            "diff_lines": len(diff_lines),
            "host_executor_v1_scoped_only": True,
        })
        return ScopedPatchPlan(
            plan_id=plan_id,
            target_path=str(resolved),
            allowed=True,
            diff_preview=diff_preview,
            rollback_patch=rollback_patch,
            risk_level="medium",
            audit_event_id=str(record.get("ts") or ""),
        )

    def apply(self, request: ScopedPatchRequest) -> ScopedPatchResult:
        plan = self.plan(request)
        if not plan.allowed:
            return ScopedPatchResult(
                plan_id=plan.plan_id,
                applied=False,
                mutation_performed=False,
                denied_reason=plan.denied_reason,
                audit_event_id=plan.audit_event_id,
                target_path=plan.target_path,
            )
        denied = self._verify_apply_permission(request, APPLY_CONFIRMATION, "scoped patch apply")
        if denied:
            return self._denied_result(plan.plan_id, plan.target_path, denied, request.operator_id)
        resolved = Path(plan.target_path)
        original = resolved.read_text(encoding="utf-8")
        updated = original.replace(request.expected_old_text, request.replacement_text, 1)
        backup_path = self._write_backup(plan.plan_id, resolved, original)
        resolved.write_text(updated, encoding="utf-8")
        record = self.gate.audit_log.append("scoped_patch_applied", {
            "allowed": True,
            "applied": True,
            "target_path": str(resolved),
            "backup_path": str(backup_path),
            "operator_id": request.operator_id,
            "reason": request.reason,
            "mutation_performed": True,
            "auto_commit": False,
            "auto_push": False,
            "host_executor_v1_scoped_only": True,
        })
        return ScopedPatchResult(
            plan_id=plan.plan_id,
            applied=True,
            mutation_performed=True,
            backup_path=str(backup_path),
            rollback_patch=plan.rollback_patch,
            audit_event_id=str(record.get("ts") or ""),
            diff_summary=_diff_summary(plan.diff_preview),
            target_path=str(resolved),
        )

    def rollback(self, request: ScopedPatchRollbackRequest) -> ScopedPatchResult:
        plan_id = f"scoped_rollback_{uuid.uuid4().hex[:16]}"
        resolved, denied = self._validate_target_path(request.target_path)
        if denied:
            return self._denied_result(plan_id, request.target_path, denied, request.operator_id)
        assert resolved is not None
        backup, denied = self._validate_backup_path(request.backup_path)
        if denied:
            return self._denied_result(plan_id, str(resolved), denied, request.operator_id)
        assert backup is not None
        denied = self._verify_apply_permission(
            ScopedPatchRequest(
                target_path=request.target_path,
                expected_old_text="rollback",
                replacement_text="rollback",
                reason="rollback",
                operator_confirmation=request.operator_confirmation,
                tier_session_id=request.tier_session_id,
                operator_id=request.operator_id,
                dry_run=False,
            ),
            ROLLBACK_CONFIRMATION,
            "scoped patch rollback",
        )
        if denied:
            return self._denied_result(plan_id, str(resolved), denied, request.operator_id)
        current = resolved.read_text(encoding="utf-8")
        previous = backup.read_text(encoding="utf-8")
        diff = _unified_diff(current, previous, resolved, from_label="current", to_label="rollback")
        resolved.write_text(previous, encoding="utf-8")
        record = self.gate.audit_log.append("scoped_patch_rollback_applied", {
            "allowed": True,
            "applied": True,
            "target_path": str(resolved),
            "backup_path": str(backup),
            "operator_id": request.operator_id,
            "mutation_performed": True,
            "auto_commit": False,
            "auto_push": False,
            "host_executor_v1_scoped_only": True,
        })
        return ScopedPatchResult(
            plan_id=plan_id,
            applied=True,
            mutation_performed=True,
            backup_path=str(backup),
            rollback_patch=diff,
            audit_event_id=str(record.get("ts") or ""),
            diff_summary=_diff_summary(diff),
            target_path=str(resolved),
        )

    def _verify_apply_permission(self, request: ScopedPatchRequest, confirmation: str, action: str) -> str:
        if self.gate.emergency_stop.is_triggered():
            return "emergency stop is active"
        if "full_file_write" not in request.required_subswitches:
            return "full_file_write must be listed in required_subswitches"
        if request.operator_confirmation != confirmation:
            return "typed confirmation phrase mismatch"
        status = self.gate.status()
        session = self.gate.session
        if self.gate.tier != AutonomyTier.FULL_HOST_AUTHORITY or session is None or not status.get("tier4_active"):
            return "Tier 4 session is not active"
        if not request.tier_session_id or request.tier_session_id != session.session_id:
            return "Tier 4 session id mismatch"
        if not session.sub_switches.full_file_write:
            return "full_file_write sub-switch is not enabled"
        permission = self.gate.verify_action(PermissionScope.FILE_WRITE, action=action, operator_id=request.operator_id)
        if not permission.get("allowed"):
            return str(permission.get("reason") or "permission denied")
        return ""

    def _validate_target_path(self, value: str) -> tuple[Path | None, str]:
        if not value:
            return None, "target_path is required"
        raw = Path(value)
        if any(part == ".." for part in raw.parts):
            return None, "path traversal is rejected"
        target = raw if raw.is_absolute() else self.project_root / raw
        resolved = target.resolve()
        root = self.project_root.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            return None, "target_path must stay inside project root"
        rel_parts = {part.lower() for part in relative.parts}
        rel_text = relative.as_posix().lower()
        if rel_text.startswith("data/") or rel_text.startswith("runtime/") or rel_text.startswith("external_repos/"):
            return None, "runtime, data, and external_repos paths are rejected"
        if any(item in rel_parts or item in rel_text for item in FORBIDDEN_PARTS):
            return None, "forbidden store, candidate, local brain, or env path"
        if relative.name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock"}:
            return None, "lockfiles are rejected in scoped patch v1"
        if relative.suffix.lower() not in TEXT_SUFFIXES:
            return None, "target must be a supported text file"
        if not self._is_allowed_relative_path(relative):
            return None, "target_path is outside scoped patch v1 allowlist"
        return resolved, ""

    def _is_allowed_relative_path(self, relative: Path) -> bool:
        rel = relative.as_posix()
        if rel.startswith("apps/web/app/") and relative.suffix.lower() in {".tsx", ".css"}:
            return True
        if rel.startswith("apps/api/app/routers/") and relative.suffix.lower() == ".py":
            return True
        if rel.startswith("packages/agentic_micro_os/") and relative.suffix.lower() == ".py" and len(relative.parts) == 3:
            return True
        if rel.startswith("packages/splatra_turbovec/") and relative.suffix.lower() == ".py" and len(relative.parts) == 3:
            return True
        if rel.startswith("docs/") and relative.suffix.lower() == ".md" and len(relative.parts) == 2:
            return True
        return False

    def _read_text_target(self, target: Path) -> tuple[str | None, str]:
        if not target.exists() or not target.is_file():
            return None, "target_path is not an existing file"
        if target.stat().st_size > self.max_file_bytes:
            return None, f"target file exceeds {self.max_file_bytes} bytes"
        data = target.read_bytes()
        if b"\x00" in data:
            return None, "binary file rejected"
        try:
            return data.decode("utf-8"), ""
        except UnicodeDecodeError:
            return None, "target must be utf-8 text"

    def _validate_backup_path(self, value: str) -> tuple[Path | None, str]:
        if not value:
            return None, "backup_path is required"
        assert self.backup_dir is not None
        raw = Path(value)
        target = raw if raw.is_absolute() else self.project_root / raw
        resolved = target.resolve()
        backup_root = self.backup_dir.resolve()
        try:
            resolved.relative_to(backup_root)
        except ValueError:
            return None, "backup_path must stay inside scoped patch backup directory"
        if not resolved.exists() or not resolved.is_file():
            return None, "backup_path does not exist"
        return resolved, ""

    def _write_backup(self, plan_id: str, target: Path, original: str) -> Path:
        assert self.backup_dir is not None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:12]
        backup_path = self.backup_dir / f"{plan_id}_{digest}{target.suffix}"
        backup_path.write_text(original, encoding="utf-8")
        return backup_path

    def _denied_plan(self, plan_id: str, target_path: str, reason: str, operator_id: str) -> ScopedPatchPlan:
        record = self.gate.audit_log.append("scoped_patch_denied", {
            "allowed": False,
            "target_path": target_path,
            "reason": reason,
            "operator_id": operator_id,
            "mutation_performed": False,
            "host_executor_v1_scoped_only": True,
        })
        return ScopedPatchPlan(
            plan_id=plan_id,
            target_path=target_path,
            allowed=False,
            denied_reason=reason,
            audit_event_id=str(record.get("ts") or ""),
        )

    def _denied_result(self, plan_id: str, target_path: str, reason: str, operator_id: str) -> ScopedPatchResult:
        record = self.gate.audit_log.append("scoped_patch_apply_denied", {
            "allowed": False,
            "applied": False,
            "target_path": target_path,
            "reason": reason,
            "operator_id": operator_id,
            "mutation_performed": False,
            "host_executor_v1_scoped_only": True,
        })
        return ScopedPatchResult(
            plan_id=plan_id,
            target_path=target_path,
            applied=False,
            mutation_performed=False,
            denied_reason=reason,
            audit_event_id=str(record.get("ts") or ""),
        )


def _unified_diff(original: str, updated: str, target: Path, from_label: str = "before", to_label: str = "after") -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=f"{from_label}:{target.as_posix()}",
            tofile=f"{to_label}:{target.as_posix()}",
            lineterm="",
        )
    )


def _diff_summary(diff: str) -> str:
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return f"+{added} -{removed}"
