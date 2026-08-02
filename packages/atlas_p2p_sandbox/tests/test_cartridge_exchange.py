from __future__ import annotations

from packages.atlas_p2p_sandbox.cartridge_exchange import evaluate_exchange
from packages.atlas_p2p_sandbox.models import SandboxCartridge
from packages.atlas_p2p_sandbox.peer_sim import SandboxNetwork


def public_cartridge() -> SandboxCartridge:
    return SandboxCartridge("cart", "sha256:x", True, "public", "cc-by-sa", ["atlas"], "summary")


def test_trusted_public_exchange_is_candidate_only():
    peer = SandboxNetwork.fixture().get_peer("peer_trusted_public")
    assert peer is not None

    result = evaluate_exchange(peer, public_cartridge())

    assert result.accepted is True
    assert result.safe_for_working_memory is True
    assert result.safe_for_local_brain is False
    assert result.real_p2p_used is False


def test_low_trust_peer_rejected():
    peer = SandboxNetwork.fixture().get_peer("peer_low_trust")
    assert peer is not None

    result = evaluate_exchange(peer, public_cartridge())

    assert result.accepted is False
    assert result.rejected_reason == "low_trust_peer"


def test_private_cartridge_rejected():
    peer = SandboxNetwork.fixture().get_peer("peer_trusted_public")
    assert peer is not None
    cartridge = SandboxCartridge("private", "sha256:p", False, "private", "cc-by-sa", [], "private", True)

    result = evaluate_exchange(peer, cartridge)

    assert result.accepted is False
    assert result.raw_private_data_exported is False
