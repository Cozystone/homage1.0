from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import checksum_payload, utc_now_iso, write_json


PRICING_MODELS = {"free", "one_time", "subscription"}
REQUIRED_TOP_LEVEL = {
    "cartridge_id",
    "name",
    "subtitle",
    "description",
    "version",
    "author",
    "category",
    "pricing",
    "license",
    "permissions",
    "safety",
    "contents",
    "provenance",
    "metadata",
}


def make_graph_cartridge(
    *,
    cartridge_id: str,
    name: str,
    subtitle: str,
    description: str,
    category: str,
    pricing: dict[str, Any],
    contents: dict[str, Any],
    provenance: dict[str, Any],
    tags: list[str] | None = None,
    author: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
    safety: dict[str, Any] | None = None,
    license_info: dict[str, Any] | None = None,
    version: str = "0.1.0",
) -> dict[str, Any]:
    now = utc_now_iso()
    payload = {
        "cartridge_id": cartridge_id,
        "name": name,
        "subtitle": subtitle,
        "description": description,
        "version": version,
        "author": author or {"name": "ATANOR", "id": "atanor", "verified": True},
        "category": category,
        "pricing": {
            "model": pricing.get("model", "free"),
            "price": pricing.get("price"),
            "currency": pricing.get("currency", "none"),
            "billing_period": pricing.get("billing_period", "none"),
            "trial_days": pricing.get("trial_days"),
        },
        "license": license_info or {
            "type": pricing.get("model", "free"),
            "terms_url": None,
            "offline_allowed": True,
            "redistribution_allowed": False,
        },
        "permissions": {
            "read_local_brain": False,
            "write_local_brain": False,
            "attach_to_working_memory": True,
            "use_cloud_context": True,
            "export_allowed": False,
            **(permissions or {}),
        },
        "safety": {
            "default_read_only": True,
            "requires_user_approval_for_local_write": True,
            "pii_safe": True,
            "trusted": True,
            "risk_level": "low",
            **(safety or {}),
        },
        "contents": {
            "seed_extensions": contents.get("seed_extensions", []),
            "semantic_graph": contents.get("semantic_graph", {"nodes": [], "edges": []}),
            "surface_graph": contents.get("surface_graph", {
                "constructions": [],
                "discourse_moves": [],
                "lemma_choices": [],
                "style_profiles": [],
            }),
            "reasoning_patterns": contents.get("reasoning_patterns", []),
            "repair_rules": contents.get("repair_rules", []),
            "evaluation_prompts": contents.get("evaluation_prompts", []),
        },
        "provenance": {
            "source_type": provenance.get("source_type", "manual_sample"),
            "source_paths": provenance.get("source_paths", []),
            "exported_from_run_id": provenance.get("exported_from_run_id"),
            "proof_store_only": bool(provenance.get("proof_store_only", True)),
            "old_mirror_snapshot_used": False,
            "verification_state": str(provenance.get("verification_state") or "unspecified"),
            "independent_source_attestation": provenance.get("independent_source_attestation") is True,
            "authoritative_for_answer": provenance.get("authoritative_for_answer") is True,
        },
        "metadata": {
            "created_at": now,
            "updated_at": now,
            "source": provenance.get("source_type", "manual_sample"),
            "checksum": "",
            "size_bytes": 0,
            "language": contents.get("language", ["ko", "en"]),
            "tags": tags or [],
        },
    }
    # Finalize every checksummed field before hashing. The fixed-width placeholder
    # breaks the size/checksum cycle without changing the final serialized length.
    payload["metadata"]["checksum"] = "0" * 64
    for _iteration in range(8):
        size_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload["metadata"]["size_bytes"] == size_bytes:
            break
        payload["metadata"]["size_bytes"] = size_bytes
    else:
        raise RuntimeError("graph_cartridge_size_bytes_did_not_converge")
    payload["metadata"]["checksum"] = checksum_payload(payload)
    return payload


def validate_cartridge_schema(cartridge: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_TOP_LEVEL - set(cartridge))
    pricing_model = str((cartridge.get("pricing") or {}).get("model") or "")
    errors = []
    if missing:
        errors.append(f"missing_top_level:{','.join(missing)}")
    if pricing_model not in PRICING_MODELS:
        errors.append("invalid_pricing_model")
    if (cartridge.get("permissions") or {}).get("write_local_brain") is True and not (cartridge.get("safety") or {}).get("requires_user_approval_for_local_write"):
        errors.append("unsafe_local_write_permission")
    if "Brain Store" in json.dumps(cartridge, ensure_ascii=False):
        errors.append("forbidden_public_name_brain_store")
    return {"valid": not errors, "errors": errors}


def verify_cartridge_checksum(path: str | Path) -> bool:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = str((payload.get("metadata") or {}).get("checksum") or "")
    return bool(expected) and expected == checksum_payload(payload)


def write_cartridge(path: str | Path, cartridge: dict[str, Any]) -> dict[str, Any]:
    validation = validate_cartridge_schema(cartridge)
    if not validation["valid"]:
        raise ValueError(";".join(validation["errors"]))
    write_json(Path(path), cartridge)
    return cartridge
