from __future__ import annotations

import pytest

from packages.local_memory_approval.models import MemoryApprovalDecision, MemoryCandidate, MemoryManifestDraft


def test_memory_candidate_rejects_local_brain_write() -> None:
    with pytest.raises(ValueError, match="cannot write Local Brain"):
        MemoryCandidate(
            candidate_id="m1",
            source_type="user_text",
            raw_text="remember this",
            normalized_summary="remember this",
            memory_type="preference",
            sensitivity="personal",
            confidence=0.8,
            source_refs=[{"ref": "local"}],
            created_at="2026-01-01T00:00:00Z",
            local_brain_write=True,
        )


def test_decision_rejects_applied_to_local_brain() -> None:
    with pytest.raises(ValueError, match="cannot be applied"):
        MemoryApprovalDecision(
            decision_id="d1",
            candidate_id="m1",
            decision="approve_for_future_memory_manifest",
            applied_to_local_brain=True,
        )


def test_manifest_rejects_apply_enabled() -> None:
    with pytest.raises(ValueError, match="cannot be ready"):
        MemoryManifestDraft(
            manifest_id="local-memory-manifest:x",
            source_session_id="s1",
            approved_candidate_ids=[],
            rejected_candidate_ids=[],
            deferred_candidate_ids=[],
            local_brain_hash_before=None,
            created_at="2026-01-01T00:00:00Z",
            canonical_hash="hash",
            apply_enabled=True,
        )
