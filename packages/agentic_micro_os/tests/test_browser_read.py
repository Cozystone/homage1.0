from packages.agentic_micro_os.browser_read import BrowserReadConnector, BrowserReadRequest
from packages.agentic_micro_os.capabilities import CapabilityKernel


def test_browser_read_accepts_public_visible_snapshot() -> None:
    kernel = CapabilityKernel()
    connector = BrowserReadConnector(kernel=kernel)
    token = kernel.issue("browser_read")

    result = connector.read(
        BrowserReadRequest(
            url="http://127.0.0.1:3041/?section=agent-os",
            visible_text="Agentic Micro-OS proof-only status",
            metadata={"section": "agent-os"},
        ),
        token,
    )

    assert result.allowed is True
    assert result.observation is not None
    assert result.observation.source == "browser_read"
    assert result.observation.metadata["fetched"] is False
    assert result.browser_automation is False
    assert result.arbitrary_js_eval is False
    assert result.private_payload_sent is False


def test_browser_read_rejects_private_or_unallowlisted_input() -> None:
    kernel = CapabilityKernel()
    connector = BrowserReadConnector(kernel=kernel)
    token = kernel.issue("browser_read")

    private_result = connector.read(
        BrowserReadRequest(
            url="http://127.0.0.1:3041",
            visible_text="raw_private_memory: do not send",
        ),
        token,
    )
    external_result = connector.read(
        BrowserReadRequest(url="https://example.com", visible_text="public"),
        token,
    )

    assert private_result.allowed is False
    assert "private" in private_result.denied_reason
    assert external_result.allowed is False
    assert "allowlisted" in external_result.denied_reason


def test_browser_read_requires_matching_capability_token() -> None:
    kernel = CapabilityKernel()
    connector = BrowserReadConnector(kernel=kernel)
    token = kernel.issue("browser_read_mock")

    result = connector.read(BrowserReadRequest(url="http://localhost:3041"), token)

    assert result.allowed is False
    assert "mismatch" in result.denied_reason
