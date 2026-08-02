from __future__ import annotations

import pytest

from packages.ego_network.seed_identity import create_seed_identity, fingerprint_identity, verify_seed_phrase


SEED = "atlas proof morning congress local relay synthetic privacy review device window archive"


def test_seed_phrase_must_be_12_words() -> None:
    with pytest.raises(ValueError):
        create_seed_identity("too short")


def test_raw_phrase_is_never_stored_and_verification_works() -> None:
    identity = create_seed_identity(SEED)
    assert identity.did.startswith("did:atanor:proof:")
    assert SEED not in str(identity.to_dict())
    assert verify_seed_phrase(SEED, identity)
    assert not verify_seed_phrase("atlas proof morning congress local relay synthetic privacy review device window wrong", identity)


def test_did_fingerprint_is_deterministic() -> None:
    one = create_seed_identity(SEED)
    two = create_seed_identity(SEED)
    assert one.did == two.did
    assert fingerprint_identity(one) == fingerprint_identity(two)
