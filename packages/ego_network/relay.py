from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cartridge import validate_cartridge_privacy
from .models import CheckoutRequest, EgoCartridge


@dataclass
class LocalRelaySimulator:
    """In-memory proof relay. It performs no network or cloud upload."""

    store: dict[str, dict[str, EgoCartridge]] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    network_used: bool = False
    real_cloud_upload: bool = False

    def checkout(self, request: CheckoutRequest, cartridge: EgoCartridge) -> dict[str, Any]:
        privacy = validate_cartridge_privacy(cartridge)
        if request.cartridge_id != cartridge.cartridge_id:
            raise ValueError("checkout request cartridge_id does not match cartridge")
        if not request.dry_run:
            raise ValueError("proof relay only accepts dry_run checkout requests")
        if not privacy["relay_allowed"]:
            result = {
                "accepted": False,
                "reason": privacy["reason"],
                "dry_run": True,
                "real_cloud_upload": False,
                "raw_private_data_exported": False,
            }
            self.audit_log.append(result)
            return result
        self.store.setdefault(request.owner_did, {})[cartridge.content_hash] = cartridge
        result = {
            "accepted": True,
            "owner_did": request.owner_did,
            "content_hash": cartridge.content_hash,
            "dry_run": True,
            "real_cloud_upload": False,
            "raw_private_data_exported": False,
        }
        self.audit_log.append(result)
        return result


_DEFAULT_RELAY = LocalRelaySimulator()


def checkout_to_local_relay(
    request: CheckoutRequest,
    cartridge: EgoCartridge,
    relay: LocalRelaySimulator | None = None,
) -> dict[str, Any]:
    return (relay or _DEFAULT_RELAY).checkout(request, cartridge)


def list_relay_cartridges(owner_did: str, relay: LocalRelaySimulator | None = None) -> list[EgoCartridge]:
    return list((relay or _DEFAULT_RELAY).store.get(owner_did, {}).values())


def fetch_from_local_relay(owner_did: str, content_hash: str, relay: LocalRelaySimulator | None = None) -> EgoCartridge | None:
    return (relay or _DEFAULT_RELAY).store.get(owner_did, {}).get(content_hash)


def purge_relay(owner_did: str, relay: LocalRelaySimulator | None = None) -> dict[str, Any]:
    target = relay or _DEFAULT_RELAY
    removed = len(target.store.get(owner_did, {}))
    target.store.pop(owner_did, None)
    event = {"purged": removed, "owner_did": owner_did, "real_cloud_upload": False}
    target.audit_log.append(event)
    return event
