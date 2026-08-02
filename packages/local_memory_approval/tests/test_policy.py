from __future__ import annotations

from packages.local_memory_approval.policy import classify_memory_candidate, recommend_memory_decision


def test_preference_is_reviewable_without_write() -> None:
    candidate = classify_memory_candidate("I prefer natural Korean explanations.", "preference")

    assert candidate.memory_type == "preference"
    assert candidate.requires_user_approval is True
    assert candidate.local_brain_write is False
    assert recommend_memory_decision(candidate) == "approve_for_future_memory_manifest"


def test_project_context_is_reviewable() -> None:
    candidate = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")

    assert candidate.memory_type == "project_context"
    assert candidate.sensitivity == "public"
    assert recommend_memory_decision(candidate) == "approve_for_future_memory_manifest"


def test_sensitive_contact_requires_edit() -> None:
    candidate = classify_memory_candidate("Email me at user@example.com or call 555-123-4567.", "user_text")

    assert candidate.memory_type == "sensitive"
    assert candidate.sensitivity == "sensitive"
    assert recommend_memory_decision(candidate) == "edit_required"


def test_voice_transcript_requires_edit_or_defer() -> None:
    clear = classify_memory_candidate("I like concise answers.", "voice_transcript")
    uncertain = classify_memory_candidate("background noise maybe inaudible", "voice_transcript")

    assert clear.source_type == "voice_transcript"
    assert recommend_memory_decision(clear) == "edit_required"
    assert recommend_memory_decision(uncertain) == "defer"
