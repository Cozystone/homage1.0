from __future__ import annotations

from .brain_access import strip_private_payload
from .capabilities import CapabilityKernel
from .models import CapabilityToken


class ExternalAPIGateway:
    def __init__(self, allowlist: list[str] | None = None, kernel: CapabilityKernel | None = None) -> None:
        self.allowlist = allowlist or ["public_docs"]
        self.kernel = kernel or CapabilityKernel()

    def read_mock(self, api_name: str, payload: dict[str, object], token: CapabilityToken | None) -> dict[str, object]:
        decision = self.kernel.decide("external_api_read_mock", token)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if api_name not in self.allowlist:
            raise PermissionError("API is not allowlisted")
        clean = strip_private_payload(payload)
        if len(clean) != len(payload):
            raise PermissionError("private payload rejected for external API")
        return {"api_name": api_name, "operation": "read_mock", "payload": clean}
