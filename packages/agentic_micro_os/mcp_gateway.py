from __future__ import annotations

from .capabilities import CapabilityKernel
from .brain_access import strip_private_payload
from .models import CapabilityToken


class MCPGateway:
    def __init__(self, allowed_descriptors: dict[str, str] | None = None, kernel: CapabilityKernel | None = None) -> None:
        self.allowed_descriptors = allowed_descriptors or {"render_preview": "sha256:render-preview-v0"}
        self.kernel = kernel or CapabilityKernel()

    def call_mock(self, descriptor: str, payload: dict[str, object], token: CapabilityToken | None) -> dict[str, object]:
        decision = self.kernel.decide("mcp_call_mock", token)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if descriptor not in self.allowed_descriptors:
            raise PermissionError("unknown MCP descriptor")
        clean = strip_private_payload(payload)
        if len(clean) != len(payload):
            raise PermissionError("private payload rejected for MCP")
        return {"descriptor": descriptor, "called": True, "payload": clean}
