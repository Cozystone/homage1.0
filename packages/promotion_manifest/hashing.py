from __future__ import annotations

import hashlib

from .canonicalize import canonical_json_bytes


def sha256_hex(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def manifest_id_for_hash(canonical_hash: str) -> str:
    return f"promotion-manifest:{canonical_hash[:16]}"
