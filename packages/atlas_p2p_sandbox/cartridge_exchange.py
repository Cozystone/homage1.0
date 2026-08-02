from __future__ import annotations

from .models import ExchangeResult, SandboxCartridge, SandboxPeer


OPEN_LICENSE_HINTS = {"cc-by", "cc-by-sa", "public-domain", "mit", "apache-2.0", "bsd"}


def evaluate_exchange(peer: SandboxPeer, cartridge: SandboxCartridge) -> ExchangeResult:
    """Evaluate a local sandbox cartridge exchange.

    The function never opens sockets, never exports raw payloads, and never marks
    a cartridge safe for Local Brain. Acceptance means working-memory/candidate
    proposal only.
    """

    if not peer.online:
        return _reject("peer_offline", peer, cartridge)
    if peer.trust_score < 0.5:
        return _reject("low_trust_peer", peer, cartridge)
    if not cartridge.public_only or cartridge.privacy_grade != "public" or cartridge.raw_payload_included:
        return _reject("private_or_raw_payload_blocked", peer, cartridge)
    if cartridge.license_hint.lower() not in OPEN_LICENSE_HINTS:
        return _reject("license_risk", peer, cartridge)
    if peer.privacy_grade == "private":
        return _reject("private_peer_not_exportable", peer, cartridge)
    return ExchangeResult(
        True,
        None,
        "atlas_p2p_sandbox_local_router",
        True,
        safe_for_local_brain=False,
        metadata={"peer_id": peer.peer_id, "cartridge_id": cartridge.cartridge_id, "proposal_only": True},
    )


def _reject(reason: str, peer: SandboxPeer, cartridge: SandboxCartridge) -> ExchangeResult:
    return ExchangeResult(
        False,
        reason,
        "atlas_p2p_sandbox_local_router",
        False,
        safe_for_local_brain=False,
        metadata={"peer_id": peer.peer_id, "cartridge_id": cartridge.cartridge_id, "proposal_only": True},
    )
