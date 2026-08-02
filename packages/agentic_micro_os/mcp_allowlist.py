from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from typing import Literal

from .brain_access import strip_private_payload
from .capabilities import CapabilityKernel
from .models import CapabilityToken


MUTATING_METHODS = {"write", "create", "update", "delete", "send", "commit", "push", "execute", "run"}


@dataclass(frozen=True)
class MCPDescriptor:
    name: str
    descriptor_hash: str
    allowed_methods: tuple[str, ...] = ("read", "validate", "render_preview")
    mutation_allowed: bool = False
    private_payload_allowed: bool = False


@dataclass(frozen=True)
class MCPValidationRequest:
    descriptor: str
    descriptor_hash: str
    method: str = "read"
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPValidationResult:
    allowed: bool
    status: Literal["allowed_mock", "denied"]
    reason: str
    descriptor: str
    method: str
    payload_hash: str = ""
    mocked_result: dict[str, object] = field(default_factory=dict)
    proof_only: bool = True
    real_mcp_called: bool = False
    local_brain_write: bool = False
    production_store_mutated: bool = False
    candidate_promotion: bool = False
    private_payload_sent: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def stable_descriptor_hash(name: str, methods: tuple[str, ...]) -> str:
    body = f"{name}:{','.join(methods)}".encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def default_descriptors() -> dict[str, MCPDescriptor]:
    render_hash = stable_descriptor_hash("render_preview", ("read", "validate", "render_preview"))
    docs_hash = stable_descriptor_hash("public_docs_lookup", ("read", "validate"))
    return {
        "render_preview": MCPDescriptor("render_preview", render_hash),
        "public_docs_lookup": MCPDescriptor("public_docs_lookup", docs_hash, ("read", "validate")),
    }


class MCPAllowlistGateway:
    """Validates MCP requests without calling a real MCP server."""

    def __init__(
        self,
        descriptors: dict[str, MCPDescriptor] | None = None,
        kernel: CapabilityKernel | None = None,
    ) -> None:
        self.descriptors = descriptors or default_descriptors()
        self.kernel = kernel or CapabilityKernel()

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "proof_only": True,
            "real_mcp_called": False,
            "descriptors": {name: asdict(descriptor) for name, descriptor in self.descriptors.items()},
        }

    def validate(self, request: MCPValidationRequest, token: CapabilityToken | None) -> MCPValidationResult:
        decision = self.kernel.decide("mcp_allowlist_validate", token)
        if not decision.allowed:
            return self._deny(request, decision.reason)

        descriptor = self.descriptors.get(request.descriptor)
        if descriptor is None:
            return self._deny(request, "unknown MCP descriptor")
        if request.descriptor_hash != descriptor.descriptor_hash:
            return self._deny(request, "descriptor hash mismatch")
        if request.method not in descriptor.allowed_methods:
            return self._deny(request, "method is not allowlisted")
        if request.method in MUTATING_METHODS or not descriptor.mutation_allowed and request.method not in {"read", "validate", "render_preview"}:
            return self._deny(request, "mutating MCP method rejected")

        clean_payload = strip_private_payload(request.payload)
        if len(clean_payload) != len(request.payload) and not descriptor.private_payload_allowed:
            return self._deny(request, "private payload rejected for MCP")

        payload_hash = hashlib.sha256(repr(sorted(clean_payload.items())).encode("utf-8")).hexdigest()
        return MCPValidationResult(
            allowed=True,
            status="allowed_mock",
            reason="descriptor and payload passed proof-only allowlist validation",
            descriptor=request.descriptor,
            method=request.method,
            payload_hash=payload_hash,
            mocked_result={"validated": True, "real_mcp_called": False, "payload": clean_payload},
        )

    @staticmethod
    def _deny(request: MCPValidationRequest, reason: str) -> MCPValidationResult:
        return MCPValidationResult(False, "denied", reason, request.descriptor, request.method)
