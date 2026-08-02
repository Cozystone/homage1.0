"""Pydantic v2 models for DataGate.

These are the public data contract. Per the handoff, invariants are enforced
by model validators so an invalid record can never be constructed:

- a ``rejected`` document MUST carry ``rejection_reason`` and ``rejected_by``
- an ``accepted`` document MUST carry ``quality_score``
- a failed ``FilterResult`` MUST carry a ``reason``
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class DocumentMetadata(BaseModel):
    doc_id: str                      # sha256(normalized_text)[:16]
    source_path: str                 # relative to data/raw
    char_count: int
    word_count: int
    line_count: int
    special_char_ratio: float        # 0.0-1.0
    link_density: float              # 0.0-1.0
    content_hash: str                # full sha256 hex
    status: Literal["accepted", "rejected"]
    rejection_reason: str | None = None   # REQUIRED (non-null) when rejected
    rejected_by: str | None = None        # filter name, when rejected
    quality_score: float | None = None    # 0-100, REQUIRED when accepted
    filters_passed: list[str] = []
    run_id: str
    processed_at: str                # ISO 8601 UTC (informational only)

    @model_validator(mode="after")
    def _enforce_status_invariants(self) -> "DocumentMetadata":
        if self.status == "rejected":
            if not self.rejection_reason or not self.rejected_by:
                raise ValueError(
                    "rejected documents require both rejection_reason and rejected_by"
                )
        if self.status == "accepted":
            if self.quality_score is None:
                raise ValueError("accepted documents require a quality_score")
        return self


class Document(BaseModel):
    doc_id: str
    source_path: str
    text: str                        # original, unmodified
    metadata: DocumentMetadata | None = None


class FilterResult(BaseModel):
    filter_name: str
    passed: bool
    reason: str | None = None        # human-readable, REQUIRED when passed=False
    metrics: dict[str, float | int] = {}

    @model_validator(mode="after")
    def _enforce_reason_on_failure(self) -> "FilterResult":
        if not self.passed and not self.reason:
            raise ValueError("a failed FilterResult requires a reason")
        return self


class RunReport(BaseModel):
    run_id: str
    state: Literal["completed", "failed"]
    total: int
    accepted: int
    rejected: int
    rejection_breakdown: dict[str, int] = {}   # filter_name -> count
    started_at: str
    finished_at: str
    error: str | None = None
