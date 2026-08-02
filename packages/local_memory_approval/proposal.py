from __future__ import annotations

from .models import MemoryCandidate, SourceType
from .policy import classify_memory_candidate


def propose_memory_review_candidate(text: str, source_type: SourceType = "selfhood_runtime_proposal") -> MemoryCandidate:
    """Create a reviewable memory proposal without writing Local Brain."""

    return classify_memory_candidate(text, source_type=source_type)
