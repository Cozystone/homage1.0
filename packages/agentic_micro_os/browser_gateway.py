from __future__ import annotations

import hashlib

from .capabilities import CapabilityKernel
from .models import AgentObservation, CapabilityToken


class BrowserGateway:
    def __init__(self, allowed_domains: list[str] | None = None, kernel: CapabilityKernel | None = None) -> None:
        self.allowed_domains = allowed_domains or ["127.0.0.1", "localhost", "docs.local"]
        self.kernel = kernel or CapabilityKernel()

    def read_mock(self, url: str, token: CapabilityToken | None) -> AgentObservation:
        decision = self.kernel.decide("browser_read_mock", token)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if not any(domain in url for domain in self.allowed_domains):
            raise PermissionError("browser domain is not allowlisted")
        summary = f"mock browser read: {url}"
        return AgentObservation("browser", hashlib.sha256(summary.encode()).hexdigest(), "public", summary, {"url": url})
