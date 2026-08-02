"""Independent regression controls for the EAD-1 JUnit receipt counter."""
from __future__ import annotations

from pathlib import Path

from scripts.evidence_answer_discrimination_ead1_eval import _pytest_counts


FIXTURE = Path(__file__).parent / "fixtures" / "ead1_nested_junit.xml"


def test_pytest_counts_sums_nested_testsuite_children() -> None:
    assert _pytest_counts(FIXTURE) == {
        "tests": 3,
        "failed": 1,
        "errors": 0,
        "skipped": 1,
        "xfailed": 0,
        "xpassed": 0,
    }
