import pytest

from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.mcp_gateway import MCPGateway


def test_mcp_unknown_and_missing_token_rejected():
    kernel = CapabilityKernel()
    gateway = MCPGateway(kernel=kernel)
    with pytest.raises(PermissionError):
        gateway.call_mock("render_preview", {}, None)
    token = kernel.issue("mcp_call_mock")
    with pytest.raises(PermissionError):
        gateway.call_mock("unknown", {}, token)
