from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from packages.cgsr.cgsr.conversation_grounding import gather_grounded_context
from packages.cgsr.cgsr.conversation_router import route_conversation_request
from packages.cgsr.cgsr.verified_fact_retrieval import retrieve_verified_facts


QUESTION = "What is the capital of France?"
TRUE_FACT = "The capital of France is Paris."
FORGED_FACT = "The capital of France is Berlin."
SOURCE_REF = "operator-curated:france"


def _write_row(tmp_path: Path, *, fact: str, metadata: dict[str, Any]) -> None:
    row = {
        "text": fact,
        "source_id": SOURCE_REF,
        **metadata,
    }
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hits(tmp_path: Path) -> list[Any]:
    return retrieve_verified_facts(QUESTION, store_path=tmp_path, limit=1)


@pytest.mark.parametrize(
    "metadata",
    [
        {"verification": {"status": "verified"}},
        {"status": "accepted"},
    ],
    ids=["schema-verification-verified", "legacy-top-level-accepted"],
)
def test_preregistered_explicit_positive_status_remains_accepted(
    tmp_path: Path,
    metadata: dict[str, Any],
) -> None:
    _write_row(tmp_path, fact=TRUE_FACT, metadata=metadata)

    hits = _hits(tmp_path)

    assert len(hits) == 1
    assert hits[0].fact == TRUE_FACT
    assert hits[0].source_ref == SOURCE_REF


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"verification": {}},
        {"status": None},
        {"status": ""},
        {"verification": {"status": None}},
        {"verification": {"status": ""}},
        {"verification": {"status": "pending"}},
        {"verification": {"status": "rejected"}},
        {"verification": {"status": "quarantined"}},
        {"verification": {"status": "VERIFIED"}},
        {"status": "accepted", "verification": {"status": "rejected"}},
    ],
    ids=[
        "no-status-field",
        "empty-verification-object",
        "null-top-level-status",
        "empty-top-level-status",
        "null-nested-status",
        "empty-nested-status",
        "pending",
        "rejected",
        "quarantined",
        "unknown-casing",
        "conflicting-positive-and-negative",
    ],
)
def test_preregistered_missing_malformed_or_conflicting_status_fails_closed(
    tmp_path: Path,
    metadata: dict[str, Any],
) -> None:
    _write_row(tmp_path, fact=FORGED_FACT, metadata=metadata)

    assert _hits(tmp_path) == []


def test_preregistered_rejected_row_cannot_create_downstream_grounding(
    tmp_path: Path,
) -> None:
    _write_row(tmp_path, fact=FORGED_FACT, metadata={})
    route = route_conversation_request(QUESTION)

    context = gather_grounded_context(
        QUESTION,
        route,
        runtime={"verified_store_path": str(tmp_path)},
    )

    assert context.facts == ()
    assert context.source_refs == ()
    assert context.grounding_source == "none"
    assert context.grounding_quality == "none"


def test_preregistered_legitimate_source_receipt_survives_downstream(
    tmp_path: Path,
) -> None:
    _write_row(
        tmp_path,
        fact=TRUE_FACT,
        metadata={"verification": {"status": "verified"}},
    )
    route = route_conversation_request(QUESTION)

    context = gather_grounded_context(
        QUESTION,
        route,
        runtime={"verified_store_path": str(tmp_path)},
    )

    assert context.facts == (TRUE_FACT,)
    assert context.source_refs == (SOURCE_REF,)
    assert context.grounding_source == "verified_store_v0_readonly"
    assert context.grounding_quality == "medium"


@pytest.mark.parametrize(
    "metadata",
    [
        {"status": "accepted", "verification": "verified"},
        {"status": "accepted", "verification": None},
        {"verification_status": []},
        {
            "status": "verified",
            "verification_status": "accepted",
            "verification": {"status": "pending"},
        },
    ],
    ids=[
        "string-verification-container",
        "null-verification-container",
        "non-string-flat-status",
        "negative-third-status",
    ],
)
def test_change_aware_malformed_container_and_status_bypasses_fail_closed(
    tmp_path: Path,
    metadata: dict[str, Any],
) -> None:
    _write_row(tmp_path, fact=FORGED_FACT, metadata=metadata)

    assert _hits(tmp_path) == []


def test_change_aware_multiple_explicit_positive_statuses_remain_accepted(
    tmp_path: Path,
) -> None:
    _write_row(
        tmp_path,
        fact=TRUE_FACT,
        metadata={
            "status": "accepted",
            "verification_status": "verified",
            "verification": {"status": "accepted"},
        },
    )

    hits = _hits(tmp_path)

    assert len(hits) == 1
    assert hits[0].fact == TRUE_FACT
    assert hits[0].source_ref == SOURCE_REF
