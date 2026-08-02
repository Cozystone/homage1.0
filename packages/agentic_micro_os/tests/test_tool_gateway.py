import pytest

from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.tool_gateway import ExternalAPIGateway


def test_external_api_private_payload_rejected():
    kernel = CapabilityKernel()
    gateway = ExternalAPIGateway(kernel=kernel)
    token = kernel.issue("external_api_read_mock")
    with pytest.raises(PermissionError):
        gateway.read_mock("public_docs", {"private_note": "secret"}, token)
