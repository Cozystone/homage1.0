from __future__ import annotations

import pytest

from packages.promotion_manifest.proof import _reviewed_session
from packages.promotion_manifest.signer import proof_sign
from packages.promotion_manifest.validator import build_manifest_from_review_session


def test_proof_sign_does_not_enable_promotion(tmp_path) -> None:
    manifest = build_manifest_from_review_session(_reviewed_session(str(tmp_path)), created_at="2026-01-01T00:00:00Z")
    signed = proof_sign(manifest, "proof-reviewer")

    assert signed.signed is True
    assert signed.signature == f"proof-signature:{manifest.canonical_hash}"
    assert signed.signer_id == "proof-reviewer"
    assert signed.ready_for_real_promotion is False
    assert signed.apply_enabled is False


def test_proof_sign_requires_signer_id(tmp_path) -> None:
    manifest = build_manifest_from_review_session(_reviewed_session(str(tmp_path)), created_at="2026-01-01T00:00:00Z")

    with pytest.raises(ValueError, match="signer_id"):
        proof_sign(manifest, "")
