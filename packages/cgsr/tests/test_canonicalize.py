from __future__ import annotations

from cgsr.canonicalize import canonicalize, dedupe_constructions
from cgsr.models import ConstructionCandidate


def _candidate(marker: str) -> ConstructionCandidate:
    return ConstructionCandidate(
        construction_id=f"cx_{marker}",
        surface_pattern=(marker, "X", "는", "Y", "입니다"),
        tag_pattern=("MAG", "NNP", "JX", "NNG", "EF"),
        abstract_pattern=(marker, "SLOT:NOUN", "는", "SLOT:NOUN", "입니다"),
        examples=[f"{marker} X는 Y입니다"],
        frequency=1,
    )


def test_near_duplicate_simplification_markers_merge() -> None:
    rows = [_candidate("쉽게 말하면"), _candidate("간단히 말해"), _candidate("쉽게는")]

    merged = dedupe_constructions(rows)

    assert len(merged) == 1
    assert merged[0].frequency == 3
    assert "SIMPLIFY_MARKER" in canonicalize(rows[0])


def test_non_equivalent_markers_do_not_merge() -> None:
    rows = [_candidate("쉽게 말하면"), _candidate("다만")]

    merged = dedupe_constructions(rows)

    assert len(merged) == 2
