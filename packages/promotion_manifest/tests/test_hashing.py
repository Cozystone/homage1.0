from __future__ import annotations

from packages.promotion_manifest.hashing import manifest_id_for_hash, sha256_hex


def test_same_content_same_hash() -> None:
    assert sha256_hex({"b": "  two ", "a": 1}) == sha256_hex({"a": 1, "b": "two"})


def test_manifest_id_is_content_addressed_prefix() -> None:
    digest = "0123456789abcdef" * 4
    assert manifest_id_for_hash(digest) == "promotion-manifest:0123456789abcdef"
