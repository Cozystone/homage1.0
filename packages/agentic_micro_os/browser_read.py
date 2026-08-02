from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from urllib.parse import urlparse

from .brain_access import strip_private_payload
from .capabilities import CapabilityKernel
from .models import AgentObservation, CapabilityToken


DEFAULT_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "docs.local"}
PRIVATE_MARKERS = ("private_", "raw_memory", "raw_private_memory", "authorization", "cookie", "token")


@dataclass(frozen=True)
class BrowserReadRequest:
    url: str
    visible_text: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    max_chars: int = 1200


@dataclass(frozen=True)
class BrowserReadResult:
    allowed: bool
    status: str
    observation: AgentObservation | None = None
    denied_reason: str = ""
    proof_only: bool = True
    browser_automation: bool = False
    arbitrary_js_eval: bool = False
    private_payload_sent: bool = False
    external_llm: bool = False
    external_sllm: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.observation is not None:
            payload["observation"] = asdict(self.observation)
        return payload


class BrowserReadConnector:
    """Reads only caller-supplied public visible text snapshots.

    This connector deliberately does not drive a browser, execute JavaScript,
    fetch private URLs, or send page content to an external model.
    """

    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        kernel: CapabilityKernel | None = None,
    ) -> None:
        self.allowed_hosts = allowed_hosts or DEFAULT_ALLOWED_HOSTS
        self.kernel = kernel or CapabilityKernel()

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "proof_only": True,
            "allowed_hosts": sorted(self.allowed_hosts),
            "network_fetch_enabled": False,
            "browser_automation": False,
            "arbitrary_js_eval": False,
            "private_payload_sent": False,
        }

    def read(self, request: BrowserReadRequest, token: CapabilityToken | None) -> BrowserReadResult:
        decision = self.kernel.decide("browser_read", token)
        if not decision.allowed:
            return BrowserReadResult(False, "denied", denied_reason=decision.reason)

        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"}:
            return BrowserReadResult(False, "denied", denied_reason="unsupported URL scheme")
        if parsed.hostname not in self.allowed_hosts:
            return BrowserReadResult(False, "denied", denied_reason="browser host is not allowlisted")

        clean_metadata = strip_private_payload(request.metadata)
        if len(clean_metadata) != len(request.metadata) or self._contains_private_marker(request.visible_text):
            return BrowserReadResult(False, "denied", denied_reason="private browser payload rejected", private_payload_sent=False)

        visible_text = " ".join(request.visible_text.split())
        if not visible_text:
            visible_text = "visible text snapshot not provided; no browser fetch was performed"
        summary = visible_text[: max(1, min(request.max_chars, 4000))]
        content_hash = hashlib.sha256(f"{request.url}\n{summary}".encode("utf-8")).hexdigest()
        observation = AgentObservation(
            source="browser_read",
            content_hash=content_hash,
            redaction_level="public_snapshot",
            summary=summary,
            metadata={"url": request.url, "fetched": False, **clean_metadata},
        )
        return BrowserReadResult(True, "read_public_snapshot", observation=observation)

    @staticmethod
    def _contains_private_marker(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in PRIVATE_MARKERS)
