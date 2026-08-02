from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from .manifest import build_memory_manifest_draft as _build_memory_manifest_draft
from .manifest import validate_memory_manifest
from .models import MemoryApprovalSession, MemoryDecision, SourceType
from .policy import classify_memory_candidate, recommend_memory_decision
from .review_store import DEFAULT_REVIEW_STORE, MemoryApprovalReviewStore


REVIEW_ROOT_ENV = "ATANOR_LOCAL_MEMORY_APPROVAL_REVIEW_ROOT"


def _store(root: Path | str | None = None) -> MemoryApprovalReviewStore:
    selected = root or os.getenv(REVIEW_ROOT_ENV) or DEFAULT_REVIEW_STORE
    return MemoryApprovalReviewStore(selected)


def _normalize_decision(decision: str) -> MemoryDecision:
    aliases = {
        "approve": "approve_for_future_memory_manifest",
        "approved": "approve_for_future_memory_manifest",
        "reject": "reject",
        "rejected": "reject",
        "defer": "defer",
        "deferred": "defer",
        "edit": "edit_required",
        "edit_required": "edit_required",
        "sensitive": "sensitive_block",
        "sensitive_block": "sensitive_block",
    }
    normalized = aliases.get(decision.strip())
    if normalized is None:
        raise ValueError(f"unsupported memory decision: {decision}")
    return normalized  # type: ignore[return-value]


def _session_payload(session: MemoryApprovalSession) -> dict[str, Any]:
    payload = session.to_dict()
    payload["candidate_recommendations"] = {
        candidate.candidate_id: recommend_memory_decision(candidate)
        for candidate in session.candidates
    }
    payload["safety"] = safety_invariants()
    return payload


def safety_invariants() -> dict[str, bool]:
    """Return the live review safety contract. This API never applies memory."""

    return {
        "real_local_brain_write": False,
        "real_local_brain_mutated": False,
        "sandbox_local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "generated_code_executed": False,
        "memory_apply_enabled": False,
        "requires_user_approval": True,
        "text_input_supported": True,
        "voice_optional": True,
    }


def create_session_from_texts(
    texts: list[str],
    source_type: SourceType = "user_text",
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Create a review session from local text snippets without writing Local Brain."""

    clean_texts = [text.strip() for text in texts if text and text.strip()]
    if not clean_texts:
        raise ValueError("at least one non-empty memory candidate text is required")
    candidates = [classify_memory_candidate(text, source_type) for text in clean_texts]
    session = _store(root).create_memory_review_session(candidates)
    return _session_payload(session)


def list_sessions(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    """List review sessions from review metadata only."""

    store = _store(root)
    if not store.root.exists():
        return []
    sessions: list[dict[str, Any]] = []
    for path in sorted(store.root.glob("memory_review_*.json")):
        session = store.load_memory_review_session(path.stem)
        sessions.append(store.summarize_memory_review_session(session.session_id))
    return sessions


def get_session(session_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    """Load a single memory approval session from review metadata."""

    return _session_payload(_store(root).load_memory_review_session(session_id))


def add_decision(
    session_id: str,
    candidate_id: str,
    decision: str,
    *,
    edited_summary: str | None = None,
    notes: str | None = None,
    reviewer: str = "user",
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Record a user review decision without applying it to Local Brain."""

    session = _store(root).add_memory_decision(
        session_id,
        candidate_id,
        _normalize_decision(decision),
        reviewer=reviewer,
        edited_summary=edited_summary,
        notes=notes,
    )
    return _session_payload(session)


def build_manifest_draft(session_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    """Build a non-applying memory manifest preview for a review session."""

    session = _store(root).load_memory_review_session(session_id)
    manifest = _build_memory_manifest_draft(session)
    validation = validate_memory_manifest(session, manifest)
    return {
        "manifest": manifest.to_dict(),
        "validation": validation,
        "safety": safety_invariants(),
        "ready_for_memory_write": False,
        "apply_enabled": False,
        "local_brain_write": False,
    }


def get_status(*, root: Path | str | None = None) -> dict[str, Any]:
    """Summarize the review surface without touching production memory."""

    store = _store(root)
    sessions = list_sessions(root=store.root)
    pending_review_count = 0
    sensitive_block_count = 0
    for summary in sessions:
        pending_review_count += int(summary.get("candidates", 0)) - int(summary.get("decisions", 0))
        decision_counts = summary.get("decision_counts", {})
        if isinstance(decision_counts, dict):
            sensitive_block_count += int(decision_counts.get("sensitive_block", 0))
    return {
        "mode": "review_only",
        "proof_review_mode": True,
        "apply_enabled": False,
        "local_brain_write": False,
        "sessions_count": len(sessions),
        "pending_review_count": max(0, pending_review_count),
        "sensitive_block_count": sensitive_block_count,
        "voice_raw_blocked": True,
        "text_input_supported": True,
        "voice_optional": True,
        "raw_voice_auto_save": False,
        "sensitive_raw_write": "blocked",
        "safety": safety_invariants(),
    }
