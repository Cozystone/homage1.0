"""Model validation: status invariants and jsonl round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from datagate import DocumentMetadata, FilterResult


def _base_kwargs(**overrides):
    kwargs = dict(
        doc_id="a1b2c3d4e5f6a7b8",
        source_path="notes/intro.md",
        char_count=1543,
        word_count=260,
        line_count=42,
        special_char_ratio=0.04,
        link_density=0.02,
        content_hash="a1b2c3d4" * 8,
        status="accepted",
        quality_score=91.5,
        filters_passed=["min_length"],
        run_id="dg-20260611-093000",
        processed_at="2026-06-11T09:30:02Z",
    )
    kwargs.update(overrides)
    return kwargs


def test_rejected_without_reason_fails():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            **_base_kwargs(status="rejected", quality_score=None, rejected_by="min_length")
        )


def test_rejected_without_rejected_by_fails():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            **_base_kwargs(
                status="rejected",
                quality_score=None,
                rejection_reason="char_count 10 < min 200",
            )
        )


def test_accepted_without_score_fails():
    with pytest.raises(ValidationError):
        DocumentMetadata(**_base_kwargs(status="accepted", quality_score=None))


def test_valid_rejected_ok():
    meta = DocumentMetadata(
        **_base_kwargs(
            status="rejected",
            quality_score=None,
            rejection_reason="char_count 10 < min 200",
            rejected_by="min_length",
        )
    )
    assert meta.status == "rejected"
    assert meta.rejection_reason and meta.rejected_by


def test_jsonl_round_trip():
    meta = DocumentMetadata(**_base_kwargs())
    line = meta.model_dump_json()
    restored = DocumentMetadata.model_validate_json(line)
    assert restored == meta


def test_filter_result_failed_requires_reason():
    with pytest.raises(ValidationError):
        FilterResult(filter_name="min_length", passed=False)
    ok = FilterResult(filter_name="min_length", passed=False, reason="too short")
    assert ok.reason == "too short"
