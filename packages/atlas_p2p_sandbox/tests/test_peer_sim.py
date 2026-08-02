from __future__ import annotations

from packages.atlas_p2p_sandbox.peer_sim import SandboxNetwork


def test_fixture_network_is_local_only():
    network = SandboxNetwork.fixture()

    assert network.real_network_enabled is False
    assert network.get_peer("peer_trusted_public") is not None
    assert network.get_peer("missing") is None
