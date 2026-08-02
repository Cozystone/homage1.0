from __future__ import annotations

from packages.atlas_p2p_sandbox.consensus import local_consensus_accepts
from packages.atlas_p2p_sandbox.peer_sim import SandboxNetwork


def test_local_consensus_accepts_trusted_online_peers():
    network = SandboxNetwork.fixture()
    peer = network.get_peer("peer_trusted_public")
    assert peer is not None

    assert local_consensus_accepts([peer]) is True


def test_local_consensus_rejects_low_average_trust():
    network = SandboxNetwork.fixture()
    low = network.get_peer("peer_low_trust")
    assert low is not None

    assert local_consensus_accepts([low]) is False
