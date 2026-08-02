from __future__ import annotations

from .models import PromotionManifest


def proof_sign(manifest: PromotionManifest, signer_id: str) -> PromotionManifest:
    """Attach a deterministic proof-only signature placeholder.

    This is not cryptographic signing, does not use private keys, and does not
    make the manifest ready or apply-enabled.
    """

    if not signer_id:
        raise ValueError("proof signer_id is required")
    return manifest.with_signature(
        signature=f"proof-signature:{manifest.canonical_hash}",
        signer_id=signer_id,
    )
