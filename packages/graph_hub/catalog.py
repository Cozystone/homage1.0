from __future__ import annotations

from typing import Any

from .audit import append_graph_hub_audit_event
from .entitlement import check_entitlement
from .models import CATALOG_PATH, read_json, write_json
from .registry import build_catalog_item, find_cartridge_file, refresh_local_catalog


def _installed_ids() -> set[str]:
    from .installer import list_installed_cartridges

    return {str(item.get("cartridge_id")) for item in list_installed_cartridges()}


def _decorate_item(item: dict[str, Any]) -> dict[str, Any]:
    pricing_model = str(item.get("pricing_model") or "free")
    entitlement = check_entitlement(str(item["cartridge_id"]), pricing_model)
    return {
        **item,
        "installed": str(item["cartridge_id"]) in _installed_ids(),
        "owned": entitlement.get("status") in {"free", "owned", "active_subscription", "trial"},
        "subscription_active": entitlement.get("status") == "active_subscription",
        "entitlement_status": entitlement.get("status", "locked"),
    }


def load_graph_hub_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        refresh_local_catalog()
    payload = read_json(CATALOG_PATH, {"items": []})
    items = payload.get("items") if isinstance(payload, dict) else []
    append_graph_hub_audit_event("catalog_viewed", None, {"product_name": "Graph Hub"}, actor="system")
    return [_decorate_item(item) for item in items if isinstance(item, dict)]


def list_catalog_items(category: str | None = None, pricing_model: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    query_l = (query or "").strip().casefold()
    rows = load_graph_hub_catalog()
    if category:
        rows = [row for row in rows if row.get("category") == category]
    if pricing_model:
        rows = [row for row in rows if row.get("pricing_model") == pricing_model]
    if query_l:
        rows = [
            row for row in rows
            if query_l in str(row.get("name", "")).casefold()
            or query_l in str(row.get("subtitle", "")).casefold()
            or query_l in " ".join(row.get("tags") or []).casefold()
        ]
    return rows


def get_catalog_item(cartridge_id: str) -> dict[str, Any]:
    for item in load_graph_hub_catalog():
        if item.get("cartridge_id") == cartridge_id:
            return item
    path = find_cartridge_file(cartridge_id)
    if not path:
        raise FileNotFoundError(cartridge_id)
    from .models import read_json

    return _decorate_item(build_catalog_item(read_json(path, {})))


def refresh_catalog() -> dict[str, Any]:
    return refresh_local_catalog()


def add_exported_cartridge_to_catalog(cartridge_path: str) -> dict[str, Any]:
    from .models import read_json

    payload = read_json(__import__("pathlib").Path(cartridge_path), {})
    item = build_catalog_item(payload)
    catalog = read_json(CATALOG_PATH, {"product_name": "Graph Hub", "items": []})
    items = [row for row in catalog.get("items", []) if row.get("cartridge_id") != item["cartridge_id"]]
    items.append(item)
    write_json(CATALOG_PATH, {"product_name": "Graph Hub", "items": items})
    return _decorate_item(item)
