from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .audit import append_graph_hub_audit_event
from .models import GRAPH_HUB_ROOT, iso_after_days, read_json, stable_id, utc_now_iso, write_json


ENTITLEMENTS_PATH = GRAPH_HUB_ROOT / "entitlements" / "entitlements.json"


def _load() -> dict[str, dict[str, Any]]:
    payload = read_json(ENTITLEMENTS_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save(payload: dict[str, dict[str, Any]]) -> None:
    write_json(ENTITLEMENTS_PATH, payload)


def _grant(cartridge_id: str, pricing_model: str, status: str, *, expires_at: str | None = None, source: str = "local_entitlement_simulation") -> dict[str, Any]:
    entitlements = _load()
    entitlement = {
        "entitlement_id": stable_id("ent", f"{cartridge_id}:{pricing_model}"),
        "cartridge_id": cartridge_id,
        "pricing_model": pricing_model,
        "status": status,
        "granted_at": utc_now_iso(),
        "expires_at": expires_at,
        "source": source,
        "metadata": {"billing_mode": "local_entitlement_simulation", "real_payment": False},
    }
    entitlements[cartridge_id] = entitlement
    _save(entitlements)
    event_type = "entitlement_granted" if pricing_model == "free" else "local_one_time_entitlement_granted" if pricing_model == "one_time" else "local_subscription_entitlement_started"
    append_graph_hub_audit_event(event_type, cartridge_id, {"status": status, "expires_at": expires_at})
    return entitlement


def grant_free_entitlement(cartridge_id: str) -> dict[str, Any]:
    return _grant(cartridge_id, "free", "free")


def grant_local_one_time_entitlement(cartridge_id: str) -> dict[str, Any]:
    return _grant(cartridge_id, "one_time", "owned")


def grant_local_subscription_entitlement(cartridge_id: str, days: int = 30) -> dict[str, Any]:
    return _grant(cartridge_id, "subscription", "active_subscription", expires_at=iso_after_days(days))


def expire_subscription(cartridge_id: str) -> dict[str, Any]:
    entitlements = _load()
    entitlement = entitlements.get(cartridge_id) or _grant(cartridge_id, "subscription", "expired_subscription", expires_at=utc_now_iso())
    entitlement["status"] = "expired_subscription"
    entitlement["expires_at"] = utc_now_iso()
    entitlements[cartridge_id] = entitlement
    _save(entitlements)
    append_graph_hub_audit_event("subscription_expired", cartridge_id, {"status": "expired_subscription"})
    return entitlement


def check_entitlement(cartridge_id: str, pricing_model: str | None = None) -> dict[str, Any]:
    entitlement = _load().get(cartridge_id)
    if not entitlement and pricing_model == "free":
        entitlement = grant_free_entitlement(cartridge_id)
    if not entitlement:
        return {"cartridge_id": cartridge_id, "status": "locked", "attach_allowed": False, "install_allowed": False}
    status = str(entitlement.get("status") or "locked")
    expires_at = entitlement.get("expires_at")
    if status == "active_subscription" and expires_at:
        try:
            if datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                entitlement = expire_subscription(cartridge_id)
                status = "expired_subscription"
        except Exception:
            pass
    allowed = status in {"free", "owned", "active_subscription", "trial"}
    return {**entitlement, "attach_allowed": allowed, "install_allowed": allowed}


def list_entitlements() -> list[dict[str, Any]]:
    return list(_load().values())
