from __future__ import annotations

from packages.promotion_manifest.canonicalize import canonical_json_bytes, normalize_whitespace


def test_whitespace_is_normalized() -> None:
    assert normalize_whitespace("  alpha\n\t beta  ") == "alpha beta"


def test_signature_and_timestamp_are_excluded_from_canonical_bytes() -> None:
    base = {
        "manifest_id": "promotion-manifest:x",
        "created_at": "2026-01-01T00:00:00Z",
        "items": [{"item_type": "concept", "candidate_id": "b", "item_id": "2"}],
        "signed": False,
        "signature": None,
        "signer_id": None,
    }
    signed = {
        **base,
        "created_at": "2026-12-31T00:00:00Z",
        "signed": True,
        "signature": "proof-signature:abc",
        "signer_id": "reviewer",
    }

    assert canonical_json_bytes(base) == canonical_json_bytes(signed)


def test_item_order_is_stable() -> None:
    first = {
        "items": [
            {"item_type": "relation", "candidate_id": "b", "item_id": "2"},
            {"item_type": "concept", "candidate_id": "a", "item_id": "1"},
        ]
    }
    second = {
        "items": [
            {"item_type": "concept", "candidate_id": "a", "item_id": "1"},
            {"item_type": "relation", "candidate_id": "b", "item_id": "2"},
        ]
    }

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
