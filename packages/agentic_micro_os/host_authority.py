from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.agentic_micro_os.permission_gate import PermissionGate, PermissionScope


SAFE_TEST_COMMANDS = {"echo", "git status"}


@dataclass
class HostAuthority:
    gate: PermissionGate

    def verify(self, scope: PermissionScope | str, action: str, operator_id: str = "operator") -> dict[str, Any]:
        return self.gate.verify_action(scope, action=action, operator_id=operator_id)

    def run_harmless_test_command(self, command: str, operator_id: str = "operator") -> dict[str, Any]:
        if command not in SAFE_TEST_COMMANDS:
            return {
                **self.gate.verify_action(PermissionScope.SHELL, action=f"blocked unsafe test command: {command}", operator_id=operator_id),
                "executed": False,
            }
        permission = self.gate.verify_action(PermissionScope.SHELL, action=f"test command: {command}", operator_id=operator_id)
        return {**permission, "executed": bool(permission["allowed"]), "command": command}

    def write_temp_file(self, path: Path, content: str, operator_id: str = "operator") -> dict[str, Any]:
        permission = self.gate.verify_action(PermissionScope.FILE_WRITE, action=f"write temp file: {path}", operator_id=operator_id)
        if not permission["allowed"]:
            return {**permission, "written": False}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {**permission, "written": True, "path": str(path)}
