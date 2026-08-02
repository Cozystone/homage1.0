from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from .models import SeedIdentity


PROOF_SALT = "atanor-ego-network-proof-only-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_seed(seed_phrase: str) -> str:
    words = seed_phrase.strip().split()
    if len(words) != 12:
        raise ValueError("proof seed phrase must contain exactly 12 words")
    return " ".join(word.lower() for word in words)


def _seed_hash(seed_phrase: str) -> str:
    normalized = _normalize_seed(seed_phrase)
    return hashlib.sha256(f"{PROOF_SALT}:{normalized}".encode("utf-8")).hexdigest()


def create_seed_identity(seed_phrase: str) -> SeedIdentity:
    """Create a deterministic proof-only did-like identity.

    The raw phrase is never stored. This is not wallet custody and not a real DID
    method; production identity must use audited cryptographic libraries.
    """

    seed_phrase_hash = _seed_hash(seed_phrase)
    public_fingerprint = hashlib.sha256(f"public:{seed_phrase_hash}".encode("utf-8")).hexdigest()[:24]
    return SeedIdentity(
        did=f"did:atanor:proof:{public_fingerprint}",
        public_fingerprint=public_fingerprint,
        seed_phrase_hash=seed_phrase_hash,
        created_at=_utc_now(),
        proof_only=True,
    )


def verify_seed_phrase(seed_phrase: str, identity: SeedIdentity) -> bool:
    """Verify a fixture seed phrase against a proof-only identity hash."""

    return _seed_hash(seed_phrase) == identity.seed_phrase_hash


def fingerprint_identity(identity: SeedIdentity) -> str:
    """Return a stable public fingerprint for a proof identity."""

    return identity.public_fingerprint
