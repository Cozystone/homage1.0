from __future__ import annotations

import json
import re
from typing import Any


EXCLUDED_HASH_FIELDS = {"signature", "signer_id", "signed", "canonical_hash", "created_at"}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_whitespace(value)
    if isinstance(value, list):
        return [canonicalize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: canonicalize_value(value[key])
            for key in sorted(value)
            if key not in EXCLUDED_HASH_FIELDS and value[key] is not None
        }
    return value


def canonical_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic hash input with signature fields excluded."""

    base = dict(payload)
    for field in EXCLUDED_HASH_FIELDS:
        base.pop(field, None)
    if "items" in base and isinstance(base["items"], list):
        base["items"] = sorted(
            base["items"],
            key=lambda item: (
                str(item.get("item_type", "")) if isinstance(item, dict) else "",
                str(item.get("candidate_id", "")) if isinstance(item, dict) else "",
                str(item.get("item_id", "")) if isinstance(item, dict) else "",
            ),
        )
    return canonicalize_value(base)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    canonical = canonical_manifest_payload(payload)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
