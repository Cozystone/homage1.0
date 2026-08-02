import pytest

from packages.agentic_micro_os.browser_gateway import BrowserGateway
from packages.agentic_micro_os.capabilities import CapabilityKernel


def test_browser_allowlist():
    kernel = CapabilityKernel()
    gateway = BrowserGateway(kernel=kernel)
    token = kernel.issue("browser_read_mock")
    assert gateway.read_mock("http://127.0.0.1:3041", token).source == "browser"
    with pytest.raises(PermissionError):
        gateway.read_mock("https://private.example.com", token)
