from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.mcp_allowlist import (
    MCPAllowlistGateway,
    MCPValidationRequest,
    default_descriptors,
)


def test_mcp_allowlist_accepts_known_descriptor_hash_without_real_call() -> None:
    kernel = CapabilityKernel()
    gateway = MCPAllowlistGateway(kernel=kernel)
    token = kernel.issue("mcp_allowlist_validate")
    descriptor = default_descriptors()["render_preview"]

    result = gateway.validate(
        MCPValidationRequest(
            descriptor="render_preview",
            descriptor_hash=descriptor.descriptor_hash,
            method="render_preview",
            payload={"scene": "orb"},
        ),
        token,
    )

    assert result.allowed is True
    assert result.real_mcp_called is False
    assert result.local_brain_write is False
    assert result.production_store_mutated is False
    assert result.candidate_promotion is False
    assert result.mocked_result["validated"] is True


def test_mcp_allowlist_rejects_hash_mismatch_mutation_and_private_payload() -> None:
    kernel = CapabilityKernel()
    gateway = MCPAllowlistGateway(kernel=kernel)
    token = kernel.issue("mcp_allowlist_validate")
    descriptor = default_descriptors()["render_preview"]

    hash_result = gateway.validate(
        MCPValidationRequest(descriptor="render_preview", descriptor_hash="sha256:bad", method="read"),
        token,
    )
    mutation_result = gateway.validate(
        MCPValidationRequest(descriptor="render_preview", descriptor_hash=descriptor.descriptor_hash, method="delete"),
        token,
    )
    private_result = gateway.validate(
        MCPValidationRequest(
            descriptor="render_preview",
            descriptor_hash=descriptor.descriptor_hash,
            method="read",
            payload={"raw_private_memory": "secret"},
        ),
        token,
    )

    assert hash_result.allowed is False
    assert "hash" in hash_result.reason
    assert mutation_result.allowed is False
    assert "method" in mutation_result.reason
    assert private_result.allowed is False
    assert "private" in private_result.reason


def test_mcp_allowlist_requires_capability_token() -> None:
    result = MCPAllowlistGateway().validate(
        MCPValidationRequest(descriptor="render_preview", descriptor_hash="sha256:any"),
        None,
    )

    assert result.allowed is False
    assert "missing" in result.reason
