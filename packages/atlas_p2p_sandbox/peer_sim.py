from __future__ import annotations

from dataclasses import dataclass

from .models import SandboxPeer


@dataclass(frozen=True)
class SandboxNetwork:
    """Local-only peer registry. It opens no sockets and has no WAN path."""

    peers: tuple[SandboxPeer, ...]
    real_network_enabled: bool = False

    @classmethod
    def fixture(cls) -> "SandboxNetwork":
        return cls(
            (
                SandboxPeer("peer_trusted_public", "public_source", 0.92, "public", True, ["cartridge_exchange"]),
                SandboxPeer("peer_low_trust", "unknown_peer", 0.2, "public", True, ["cartridge_exchange"]),
                SandboxPeer("peer_private", "local_only", 0.9, "private", True, ["local_review"]),
            )
        )

    def get_peer(self, peer_id: str) -> SandboxPeer | None:
        for peer in self.peers:
            if peer.peer_id == peer_id:
                return peer
        return None
