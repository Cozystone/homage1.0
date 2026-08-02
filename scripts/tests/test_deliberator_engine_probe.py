"""Measurement-contract tests for the DELIBERATOR engine probe."""
from __future__ import annotations

import hashlib
import json

from scripts import deliberator_engine_probe as probe


def test_probe_schema_is_distinct_from_stale_v2_reports() -> None:
    assert probe.PROBE_SCHEMA == "atanor.deliberator.engine_probe.v3"


def test_exact_mcnemar_uses_only_discordant_pairs() -> None:
    assert probe._mcnemar_exact_two_sided(0, 0) == 1.0
    assert probe._mcnemar_exact_two_sided(1, 0) == 1.0
    assert probe._mcnemar_exact_two_sided(8, 0) == 0.0078125
    assert probe._mcnemar_exact_two_sided(4, 4) == 1.0


def test_item_ids_are_deterministic_without_exposing_item_text() -> None:
    item = {
        "q": "private licensed stem",
        "choices": {"A": "alpha", "B": "beta"},
        "gold": "B",
    }
    identifier = probe._item_id(item)

    assert identifier == probe._item_id(dict(item))
    assert len(identifier) == 64
    assert identifier == hashlib.sha256(
        json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert item["q"] not in identifier


def test_run_ids_are_unique_and_benchmark_scoped() -> None:
    first = probe._new_run_id("gpqa")
    second = probe._new_run_id("gpqa")

    assert first != second
    assert "_gpqa_" in first
