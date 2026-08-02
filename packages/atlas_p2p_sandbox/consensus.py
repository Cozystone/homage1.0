from __future__ import annotations

from .models import SandboxPeer


def local_consensus_accepts(peers: list[SandboxPeer], *, min_trust: float = 0.7) -> bool:
    """Return a deterministic local-only consensus decision."""

    if not peers:
        return False
    online = [peer for peer in peers if peer.online]
    if not online:
        return False
    average_trust = sum(peer.trust_score for peer in online) / len(online)
    return average_trust >= min_trust
