from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import CapabilityDecision, CapabilityToken


FORBIDDEN_CAPABILITIES = {
    "unrestricted_shell",
    "arbitrary_js_eval",
    "local_brain_direct_write",
    "production_store_direct_write",
    "candidate_promotion",
    "git_commit",
    "git_push",
    "microphone_enable",
    "private_file_read_unscoped",
    "network_upload_private_data",
}

ALLOWED_PROOF_CAPABILITIES = {
    "read_cell_file",
    "write_cell_patch_manifest",
    "run_cell_test_mock",
    "render_preview_mock",
    "browser_read",
    "browser_read_mock",
    "external_api_read_mock",
    "mcp_allowlist_validate",
    "mcp_call_mock",
    "splatra_cosmos_evaluate",
    "splatra_scene_command",
    "splatra_scene_choreography",
    "cloud_brain_verified_read_summary",
    "cloud_brain_candidate_write_draft",
    "local_brain_read_redacted_summary",
    "local_brain_memory_candidate_draft",
    "cloud_voice_request_mock",
    "dashboard_action",
    "request_human_approval",
}


class CapabilityKernel:
    def issue(self, capability: str, scope: str = "proof", max_calls: int = 1, reason: str = "proof") -> CapabilityToken:
        if capability in FORBIDDEN_CAPABILITIES:
            raise ValueError(f"forbidden capability cannot be issued: {capability}")
        if capability not in ALLOWED_PROOF_CAPABILITIES:
            raise ValueError(f"unknown proof capability: {capability}")
        return CapabilityToken(
            token_id=str(uuid4()),
            capability=capability,
            scope=scope,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            max_calls=max_calls,
            issued_by="agentic_micro_os_proof",
            reason=reason,
        )

    def decide(self, capability: str, token: CapabilityToken | None) -> CapabilityDecision:
        if capability in FORBIDDEN_CAPABILITIES:
            return CapabilityDecision(False, f"forbidden capability: {capability}", True, "critical")
        if capability not in ALLOWED_PROOF_CAPABILITIES:
            return CapabilityDecision(False, f"unknown capability: {capability}", True, "high")
        if token is None:
            return CapabilityDecision(False, "missing capability token", True, "medium")
        if token.capability != capability:
            return CapabilityDecision(False, "token capability mismatch", True, "medium")
        if token.expired():
            return CapabilityDecision(False, "expired capability token", True, "medium")
        if token.max_calls <= 0:
            return CapabilityDecision(False, "capability token call budget exhausted", True, "medium")
        if not token.proof_only:
            return CapabilityDecision(False, "non-proof token rejected in v0", True, "high")
        return CapabilityDecision(True, "allowed proof capability", False, "low")
