from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import subprocess
import sys
import uuid
from typing import Any

from packages.agentic_micro_os.permission_gate import PermissionGate, PermissionScope


SAFE_TEST_TOKEN = "SIGNED_SAFE_TEST"


def _safe_test_token_enabled() -> bool:
    """The SAFE_TEST_TOKEN is a UNIT-TEST convenience that downgrades SHELL/FILE scopes to
    READ_SUMMARY so tests don't need a real operator grant. In a live API it is a universal
    auth bypass, so it is honored ONLY under a test runner or an explicit opt-in env — never
    by default. (Codex audit P0: fixed public test-token file access.)"""
    if os.getenv("ATANOR_ALLOW_SAFE_TEST_TOKEN") == "1":
        return True
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
REJECTED_V0_ACTIONS = {
    "delete_file",
    "recursive_delete",
    "overwrite_non_temp_file",
    "run_arbitrary_command",
    "powershell_unrestricted",
    "network_upload",
    "credential_read",
    "browser_private_session",
    "git_commit",
    "git_push",
    "local_brain_write",
    "cloud_production_write",
    "production_store_write",
}


@dataclass(frozen=True)
class HostExecutionRequest:
    action_type: str
    path: str = ""
    content: str = ""
    max_bytes: int = 4096
    max_entries: int = 50
    safe_test_token: str = ""
    operator_id: str = "operator"


@dataclass
class HostExecutionResult:
    action_id: str
    action_type: str
    allowed: bool
    executed: bool
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    exit_code: int | None = None
    denied_reason: str = ""
    audit_event_id: str = ""
    mutation_performed: bool = False
    path_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HostExecutor:
    gate: PermissionGate
    project_root: Path
    runtime_tmp_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.runtime_tmp_dir is None:
            self.runtime_tmp_dir = self.project_root / "runtime" / "agentic_micro_os" / "tmp"

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "proof_only": True,
            "safe_test_token_name": SAFE_TEST_TOKEN,
            "runtime_tmp_dir": str(self.runtime_tmp_dir),
            "allowed_v0_actions": [
                "echo",
                "git_status",
                "read_text_file",
                "list_directory",
                "write_temp_file",
                "create_backup_patch",
                "check_emergency_stop",
            ],
            "rejected_v0_actions": sorted(REJECTED_V0_ACTIONS),
            "permission_gate": self.gate.status(),
        }

    def execute(self, request: HostExecutionRequest) -> HostExecutionResult:
        action = request.action_type.strip()
        action_id = f"hostexec_{uuid.uuid4().hex[:16]}"
        if action in REJECTED_V0_ACTIONS:
            return self._reject(action_id, request, f"{action} is rejected in Host Executor v0", PermissionScope.CODE_EXECUTION)
        if action == "check_emergency_stop":
            permission = self.gate.verify_action(PermissionScope.READ_SUMMARY, action=action, operator_id=request.operator_id)
            if not permission["allowed"]:
                return self._from_permission(action_id, request, permission)
            return HostExecutionResult(
                action_id=action_id,
                action_type=action,
                allowed=True,
                executed=True,
                stdout_excerpt=f"emergency_stop={self.gate.emergency_stop.is_triggered()}",
                audit_event_id=_audit_id(permission),
            )
        if action == "echo":
            return self._echo(action_id, request)
        if action == "git_status":
            return self._git_status(action_id, request)
        if action == "write_temp_file":
            return self._write_temp_file(action_id, request)
        if action == "read_text_file":
            return self._read_text_file(action_id, request)
        if action == "list_directory":
            return self._list_directory(action_id, request)
        if action == "create_backup_patch":
            return self._create_backup_patch(action_id, request)
        return self._reject(action_id, request, f"unknown or unsupported host executor action: {action}", PermissionScope.CODE_EXECUTION)

    def _echo(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        permission = self._verify_safe_test_or_scope(request, PermissionScope.SHELL, "echo")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=_excerpt(request.content or "ok"),
            exit_code=0,
            audit_event_id=_audit_id(permission),
        )

    def _git_status(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        permission = self._verify_safe_test_or_scope(request, PermissionScope.SHELL, "git status")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=_excerpt(completed.stdout),
            stderr_excerpt=_excerpt(completed.stderr),
            exit_code=completed.returncode,
            audit_event_id=_audit_id(permission),
        )

    def _write_temp_file(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        target = self._resolve_runtime_tmp_path(request.path or f"{action_id}.txt")
        if target is None:
            return self._reject(action_id, request, "write_temp_file path must stay under runtime/agentic_micro_os/tmp", PermissionScope.FILE_WRITE)
        permission = self._verify_safe_test_or_scope(request, PermissionScope.FILE_WRITE, f"write temp file: {target}")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.content, encoding="utf-8")
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=f"wrote {len(request.content.encode('utf-8'))} bytes",
            exit_code=0,
            audit_event_id=_audit_id(permission),
            mutation_performed=True,
            path_refs=[str(target)],
        )

    def _read_text_file(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        target = self._resolve_path(request.path)
        permission = self._verify_safe_test_or_scope(request, PermissionScope.FILE_READ, f"read text file: {target}")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        if not target.exists() or not target.is_file():
            return self._reject(action_id, request, "path is not a readable file", PermissionScope.FILE_READ)
        max_bytes = max(1, min(request.max_bytes, 64_000))
        data = target.read_bytes()[:max_bytes]
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=_excerpt(data.decode("utf-8", errors="replace")),
            exit_code=0,
            audit_event_id=_audit_id(permission),
            path_refs=[str(target)],
        )

    def _list_directory(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        target = self._resolve_path(request.path or ".")
        permission = self._verify_safe_test_or_scope(request, PermissionScope.FILE_READ, f"list directory: {target}")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        if not target.exists() or not target.is_dir():
            return self._reject(action_id, request, "path is not a readable directory", PermissionScope.FILE_READ)
        max_entries = max(1, min(request.max_entries, 200))
        entries = [entry.name for entry in sorted(target.iterdir(), key=lambda item: item.name.lower())[:max_entries]]
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=_excerpt("\n".join(entries)),
            exit_code=0,
            audit_event_id=_audit_id(permission),
            path_refs=[str(target)],
        )

    def _create_backup_patch(self, action_id: str, request: HostExecutionRequest) -> HostExecutionResult:
        target = self._resolve_runtime_tmp_path(request.path or f"{action_id}.patch")
        if target is None or target.suffix.lower() != ".patch":
            return self._reject(action_id, request, "backup patch must be a .patch file under runtime tmp", PermissionScope.FILE_WRITE)
        permission = self._verify_safe_test_or_scope(request, PermissionScope.FILE_WRITE, f"create backup patch: {target}")
        if not permission["allowed"]:
            return self._from_permission(action_id, request, permission)
        completed = subprocess.run(
            ["git", "diff", "--binary"],
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(completed.stdout, encoding="utf-8")
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=True,
            executed=True,
            stdout_excerpt=f"backup patch bytes={len(completed.stdout.encode('utf-8'))}",
            stderr_excerpt=_excerpt(completed.stderr),
            exit_code=completed.returncode,
            audit_event_id=_audit_id(permission),
            mutation_performed=True,
            path_refs=[str(target)],
        )

    def _verify_safe_test_or_scope(self, request: HostExecutionRequest, scope: PermissionScope, action: str) -> dict[str, Any]:
        if (request.safe_test_token == SAFE_TEST_TOKEN and _safe_test_token_enabled()
                and scope in {PermissionScope.SHELL, PermissionScope.FILE_READ, PermissionScope.FILE_WRITE}):
            return self.gate.verify_action(PermissionScope.READ_SUMMARY, action=f"safe-test {action}", operator_id=request.operator_id)
        return self.gate.verify_action(scope, action=action, operator_id=request.operator_id)

    def _reject(self, action_id: str, request: HostExecutionRequest, reason: str, scope: PermissionScope) -> HostExecutionResult:
        record = self.gate.audit_log.append("host_executor_denied", {
            "action": request.action_type,
            "allowed": False,
            "executed": False,
            "reason": reason,
            "scope": scope.value,
            "operator_id": request.operator_id,
        })
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=False,
            executed=False,
            denied_reason=reason,
            audit_event_id=record["ts"],
        )

    def _from_permission(self, action_id: str, request: HostExecutionRequest, permission: dict[str, Any]) -> HostExecutionResult:
        return HostExecutionResult(
            action_id=action_id,
            action_type=request.action_type,
            allowed=False,
            executed=False,
            denied_reason=str(permission.get("reason") or "permission denied"),
            audit_event_id=_audit_id(permission),
        )

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _resolve_runtime_tmp_path(self, value: str) -> Path | None:
        assert self.runtime_tmp_dir is not None
        base = self.runtime_tmp_dir.resolve()
        raw = Path(value)
        target = raw if raw.is_absolute() else base / raw
        resolved = target.resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            return None
        return resolved


def _audit_id(permission: dict[str, Any]) -> str:
    record = permission.get("audit_record")
    if isinstance(record, dict):
        return str(record.get("ts") or "")
    return ""


def _excerpt(value: str, limit: int = 1200) -> str:
    text = value.replace("\r\n", "\n")
    return text[:limit]
