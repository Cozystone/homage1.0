from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any
import uuid

from packages.agentic_micro_os.emergency_stop import DEFAULT_EMERGENCY_STOP_PATH, EmergencyStop
from packages.agentic_micro_os.host_audit_log import DEFAULT_HOST_AUDIT_LOG_PATH, HostAuditLog
from packages.agentic_micro_os.operator_confirm import FULL_HOST_CONFIRMATION_PHRASE, verify_full_host_phrase


class AutonomyTier(str, Enum):
    OBSERVE_ONLY = "OBSERVE_ONLY"
    DRAFT_PROPOSAL = "DRAFT_PROPOSAL"
    SIGNED_DELEGATION = "SIGNED_DELEGATION"
    FULL_HOST_AUTHORITY = "FULL_HOST_AUTHORITY"


class PermissionScope(str, Enum):
    READ_SUMMARY = "read_summary"
    REVIEW_DRAFT_WRITE = "review_draft_write"
    PATCH_PROPOSAL = "patch_proposal"
    SHELL = "shell"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    GIT_STATUS = "git_status"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    LOCAL_BRAIN_WRITE = "local_brain_write"
    CLOUD_PRODUCTION_WRITE = "cloud_production_write"
    EXTERNAL_NETWORK = "external_network"
    BROWSER_CONTROL = "browser_control"
    MCP_TOOLS = "mcp_tools"
    CODE_EXECUTION = "code_execution"


OUTSIDE_TIER4_INVARIANTS = {
    "external_llm": False,
    "external_sllm": False,
    "local_brain_write": False,
    "production_store_mutated": False,
    "candidate_promotion": False,
    "unrestricted_shell": False,
    "arbitrary_js_eval": False,
    "auto_commit": False,
    "auto_push": False,
}


def _state_synchronized(method: Any) -> Any:
    """Keep session rotation and authorization in one process-local boundary."""

    @wraps(method)
    def wrapped(self: "PermissionGate", *args: Any, **kwargs: Any) -> Any:
        with self._state_lock:
            return method(self, *args, **kwargs)

    return wrapped


@dataclass
class AutonomySubSwitches:
    shell: bool = False
    full_file_read: bool = False
    full_file_write: bool = False
    git_commit: bool = False
    git_push: bool = False
    local_brain_write: bool = False
    cloud_production_write: bool = False
    external_network: bool = False
    browser_control: bool = False
    mcp_tools: bool = False
    code_execution: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "AutonomySubSwitches":
        if not value:
            return cls()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: bool(item) for key, item in value.items() if key in allowed})


@dataclass
class HostAuthoritySession:
    session_id: str
    tier: AutonomyTier
    enabled_by: str
    typed_phrase: str
    started_at: str
    expires_at: str
    max_runtime_sec: int
    sub_switches: AutonomySubSwitches
    audit_log_path: str
    emergency_stop_path: str
    mutation_count: int = 0
    shell_count: int = 0
    file_write_count: int = 0
    git_action_count: int = 0

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return current >= datetime.fromisoformat(self.expires_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "tier": self.tier.value,
            "sub_switches": self.sub_switches.to_dict(),
            "expired": self.is_expired(),
        }


@dataclass
class SignedDelegation:
    token_id: str
    scopes: list[PermissionScope]
    expires_at: str
    bound_session_id: str | None = None
    bound_operator_id: str | None = None

    def allows(self, scope: PermissionScope) -> bool:
        return scope in self.scopes and datetime.now(timezone.utc) < datetime.fromisoformat(self.expires_at)


@dataclass
class PermissionGate:
    tier: AutonomyTier = AutonomyTier.DRAFT_PROPOSAL
    session: HostAuthoritySession | None = None
    signed_delegations: dict[str, SignedDelegation] = field(default_factory=dict)
    audit_log: HostAuditLog = field(default_factory=lambda: HostAuditLog(DEFAULT_HOST_AUDIT_LOG_PATH))
    emergency_stop: EmergencyStop = field(default_factory=lambda: EmergencyStop(DEFAULT_EMERGENCY_STOP_PATH))
    _state_lock: Any = field(default_factory=RLock, init=False, repr=False, compare=False)

    @_state_synchronized
    def set_tier(self, tier: AutonomyTier | str, operator_id: str = "operator") -> dict[str, Any]:
        next_tier = AutonomyTier(tier)
        if next_tier == AutonomyTier.FULL_HOST_AUTHORITY:
            result = self._deny("tier_set", "Tier 4 requires full-host enable flow", PermissionScope.CODE_EXECUTION, operator_id)
            return result
        self.tier = next_tier
        if self.session:
            self.session = None
        return self._allow("tier_set", f"tier set to {next_tier.value}", PermissionScope.READ_SUMMARY, operator_id)

    @_state_synchronized
    def issue_signed_delegation(self, scopes: list[PermissionScope], max_runtime_sec: int = 600) -> dict[str, Any]:
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(1, min(max_runtime_sec, 3600)))
        token_id = f"delegation_{uuid.uuid4().hex[:16]}"
        self.status()  # expire a stale host session before binding the delegation
        session = (
            self.session
            if self.tier == AutonomyTier.FULL_HOST_AUTHORITY
            else None
        )
        self.signed_delegations[token_id] = SignedDelegation(
            token_id,
            scopes,
            expires.isoformat(),
            bound_session_id=session.session_id if session else None,
            bound_operator_id=session.enabled_by if session else None,
        )
        return {
            "token_id": token_id,
            "expires_at": expires.isoformat(),
            "scopes": [scope.value for scope in scopes],
            "bound_session_id": session.session_id if session else None,
            "bound_operator_id": session.enabled_by if session else None,
        }

    @_state_synchronized
    def verify_bound_operator_action(
        self,
        scope: PermissionScope | str,
        *,
        signed_token: str | None,
        action: str = "",
    ) -> dict[str, Any]:
        """Authorize an HTTP mutation only through a server-held operator session.

        A caller-provided identity string is never authority.  The bearer token
        must have been minted while the current full-host session was active,
        must remain bound to that exact session and operator, and must carry the
        requested scope.  The normal full-host sub-switch, expiry, emergency
        stop, counter, and audit checks still run after the binding check.
        """

        permission_scope = PermissionScope(scope)
        self.status()  # fail closed and clear an expired session
        session = self.session
        fixed_actor = (
            session.enabled_by
            if session is not None
            else "unbound_operator_request"
        )
        if self.emergency_stop.is_triggered():
            return self._deny(
                action or "verify_bound_operator_action",
                "emergency stop is active",
                permission_scope,
                fixed_actor,
            )
        if (
            self.tier != AutonomyTier.FULL_HOST_AUTHORITY
            or session is None
        ):
            return self._deny(
                action or "verify_bound_operator_action",
                "server-bound operator session is not active",
                permission_scope,
                fixed_actor,
            )
        delegation = self.signed_delegations.get(signed_token or "")
        if (
            delegation is None
            or delegation.bound_session_id != session.session_id
            or delegation.bound_operator_id != session.enabled_by
        ):
            return self._deny(
                action or "verify_bound_operator_action",
                "server-bound operator delegation is missing or invalid",
                permission_scope,
                session.enabled_by,
            )
        if not delegation.allows(permission_scope):
            return self._deny(
                action or "verify_bound_operator_action",
                "server-bound operator delegation lacks the required scope or expired",
                permission_scope,
                session.enabled_by,
            )
        result = self._verify_full_host_action(
            permission_scope,
            action,
            session.enabled_by,
        )
        return {
            **result,
            "bound_operator_id": session.enabled_by,
            "bound_session_id": session.session_id,
        }

    @_state_synchronized
    def enable_full_host(
        self,
        *,
        enabled_by: str,
        typed_phrase: str,
        duration_sec: int,
        sub_switches: AutonomySubSwitches | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.emergency_stop.is_triggered():
            return self._deny("full_host_enable", "emergency stop is active", PermissionScope.CODE_EXECUTION, enabled_by)
        if not verify_full_host_phrase(typed_phrase):
            return self._deny("full_host_enable", "typed confirmation phrase mismatch", PermissionScope.CODE_EXECUTION, enabled_by)
        if duration_sec <= 0:
            return self._deny("full_host_enable", "duration is required", PermissionScope.CODE_EXECUTION, enabled_by)
        if duration_sec > 21600:
            return self._deny("full_host_enable", "duration exceeds 6 hour maximum", PermissionScope.CODE_EXECUTION, enabled_by)
        switches = sub_switches if isinstance(sub_switches, AutonomySubSwitches) else AutonomySubSwitches.from_mapping(sub_switches)
        now = datetime.now(timezone.utc)
        self.tier = AutonomyTier.FULL_HOST_AUTHORITY
        self.session = HostAuthoritySession(
            session_id=f"host_{uuid.uuid4().hex[:16]}",
            tier=AutonomyTier.FULL_HOST_AUTHORITY,
            enabled_by=enabled_by,
            typed_phrase=typed_phrase,
            started_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=duration_sec)).isoformat(),
            max_runtime_sec=duration_sec,
            sub_switches=switches,
            audit_log_path=str(self.audit_log.path),
            emergency_stop_path=str(self.emergency_stop.path),
        )
        return self._allow("full_host_enable", "full host authority enabled", PermissionScope.CODE_EXECUTION, enabled_by)

    @_state_synchronized
    def disable_full_host(self, operator_id: str = "operator", reason: str = "operator disabled") -> dict[str, Any]:
        self.session = None
        if self.tier == AutonomyTier.FULL_HOST_AUTHORITY:
            self.tier = AutonomyTier.DRAFT_PROPOSAL
        return self._allow("full_host_disable", reason, PermissionScope.READ_SUMMARY, operator_id)

    @_state_synchronized
    def trigger_emergency_stop(self, operator_id: str = "operator", reason: str = "operator emergency stop") -> dict[str, Any]:
        self.emergency_stop.trigger(reason)
        self.session = None
        if self.tier == AutonomyTier.FULL_HOST_AUTHORITY:
            self.tier = AutonomyTier.DRAFT_PROPOSAL
        return self._deny("emergency_stop", reason, PermissionScope.CODE_EXECUTION, operator_id)

    @_state_synchronized
    def verify_action(
        self,
        scope: PermissionScope | str,
        *,
        action: str = "",
        operator_id: str = "operator",
        signed_token: str | None = None,
    ) -> dict[str, Any]:
        permission_scope = PermissionScope(scope)
        if self.emergency_stop.is_triggered():
            return self._deny(action or "verify_action", "emergency stop is active", permission_scope, operator_id)
        if self.tier == AutonomyTier.OBSERVE_ONLY:
            allowed = permission_scope == PermissionScope.READ_SUMMARY
            return self._allow_or_deny(allowed, action, permission_scope, operator_id, "Tier 1 observe only")
        if self.tier == AutonomyTier.DRAFT_PROPOSAL:
            allowed = permission_scope in {
                PermissionScope.READ_SUMMARY,
                PermissionScope.REVIEW_DRAFT_WRITE,
                PermissionScope.PATCH_PROPOSAL,
            }
            return self._allow_or_deny(allowed, action, permission_scope, operator_id, "Tier 2 draft proposal only")
        if self.tier == AutonomyTier.SIGNED_DELEGATION:
            delegation = self.signed_delegations.get(signed_token or "")
            allowed = bool(delegation and delegation.allows(permission_scope))
            return self._allow_or_deny(allowed, action, permission_scope, operator_id, "Tier 3 requires signed scoped token")
        return self._verify_full_host_action(permission_scope, action, operator_id)

    @_state_synchronized
    def status(self) -> dict[str, Any]:
        if self.session and self.session.is_expired():
            self.session = None
            self.tier = AutonomyTier.DRAFT_PROPOSAL
        tier4_active = self.tier == AutonomyTier.FULL_HOST_AUTHORITY and self.session is not None
        return {
            **({} if tier4_active else OUTSIDE_TIER4_INVARIANTS),
            "tier": self.tier.value,
            "tier4_active": tier4_active,
            "session": self.session.to_dict() if self.session else None,
            "legacy_confirmation_phrase_authoritative": False,
            "required_boundary": "common_operator_run_lease_gate",
            "max_duration_sec": 21600,
            "duration_options_sec": [600, 1800, 7200],
            "sub_switches": self.session.sub_switches.to_dict() if self.session else AutonomySubSwitches().to_dict(),
            **self.audit_log.status(),
            **self.emergency_stop.status(),
        }

    def _verify_full_host_action(self, scope: PermissionScope, action: str, operator_id: str) -> dict[str, Any]:
        if not self.session:
            return self._deny(action or "verify_action", "Tier 4 session is not active", scope, operator_id)
        if self.session.is_expired():
            self.session = None
            self.tier = AutonomyTier.DRAFT_PROPOSAL
            return self._deny(action or "verify_action", "Tier 4 session expired", scope, operator_id)
        switches = self.session.sub_switches
        switch_map = {
            PermissionScope.READ_SUMMARY: True,
            PermissionScope.REVIEW_DRAFT_WRITE: True,
            PermissionScope.PATCH_PROPOSAL: True,
            PermissionScope.SHELL: switches.shell,
            PermissionScope.FILE_READ: switches.full_file_read,
            PermissionScope.FILE_WRITE: switches.full_file_write,
            PermissionScope.GIT_STATUS: switches.shell,
            PermissionScope.GIT_COMMIT: switches.git_commit,
            PermissionScope.GIT_PUSH: switches.git_push,
            PermissionScope.LOCAL_BRAIN_WRITE: switches.local_brain_write,
            PermissionScope.CLOUD_PRODUCTION_WRITE: switches.cloud_production_write,
            PermissionScope.EXTERNAL_NETWORK: switches.external_network,
            PermissionScope.BROWSER_CONTROL: switches.browser_control,
            PermissionScope.MCP_TOOLS: switches.mcp_tools,
            PermissionScope.CODE_EXECUTION: switches.code_execution,
        }
        allowed = bool(switch_map.get(scope, False))
        result = self._allow_or_deny(allowed, action, scope, operator_id, f"Tier 4 sub-switch {scope.value}")
        if allowed:
            self._increment_counters(scope)
        return result

    def _increment_counters(self, scope: PermissionScope) -> None:
        if not self.session:
            return
        if scope in {
            PermissionScope.FILE_WRITE,
            PermissionScope.GIT_COMMIT,
            PermissionScope.GIT_PUSH,
            PermissionScope.LOCAL_BRAIN_WRITE,
            PermissionScope.CLOUD_PRODUCTION_WRITE,
        }:
            self.session.mutation_count += 1
        if scope == PermissionScope.SHELL:
            self.session.shell_count += 1
        if scope == PermissionScope.FILE_WRITE:
            self.session.file_write_count += 1
        if scope in {PermissionScope.GIT_COMMIT, PermissionScope.GIT_PUSH, PermissionScope.GIT_STATUS}:
            self.session.git_action_count += 1

    def _allow_or_deny(self, allowed: bool, action: str, scope: PermissionScope, operator_id: str, reason: str) -> dict[str, Any]:
        if allowed:
            return self._allow(action or "verify_action", reason, scope, operator_id)
        return self._deny(action or "verify_action", reason, scope, operator_id)

    def _allow(self, action: str, reason: str, scope: PermissionScope, operator_id: str) -> dict[str, Any]:
        record = self.audit_log.append("permission_allowed", {
            "action": action,
            "allowed": True,
            "reason": reason,
            "scope": scope.value,
            "operator_id": operator_id,
            "tier": self.tier.value,
        })
        return {
            "allowed": True,
            "reason": reason,
            "action": action,
            "scope": scope.value,
            "tier": self.tier.value,
            "audit_record": record,
            **self.status(),
        }

    def _deny(self, action: str, reason: str, scope: PermissionScope, operator_id: str) -> dict[str, Any]:
        record = self.audit_log.append("permission_denied", {
            "action": action,
            "allowed": False,
            "reason": reason,
            "scope": scope.value,
            "operator_id": operator_id,
            "tier": self.tier.value,
        })
        return {
            "allowed": False,
            "reason": reason,
            "action": action,
            "scope": scope.value,
            "tier": self.tier.value,
            "audit_record": record,
            **self.status(),
        }


def gate_for_test(tmp_path: Path) -> PermissionGate:
    return PermissionGate(
        audit_log=HostAuditLog(tmp_path / "host_audit.jsonl"),
        emergency_stop=EmergencyStop(tmp_path / "EMERGENCY_STOP"),
    )
