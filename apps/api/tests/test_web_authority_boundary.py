"""Preregistered security boundary for live web-answer authority.

The dataset and numeric gates were frozen before the production fix.  These
tests exercise the real extractive answer surface, not a replica of the
authority helper.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.web_search import _WEB_HEDGE_EN, compose_web_answer


_DATASET_PATH = (
    _REPO_ROOT / "data" / "eval" / "pattern_05_web_authority_dataset_v1.json"
)
_DATASET = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
_CASES = _DATASET["cases"]


def _cases(kind: str) -> list[dict[str, object]]:
    return [case for case in _CASES if case["kind"] == kind]


def _compose(case: dict[str, object]) -> dict[str, object]:
    result = compose_web_answer(
        str(case["query"]),
        [dict(case["row"])],
        language=str(case["language"]),
    )
    assert result is not None, case["item_id"]
    return result


def _compose_rows(rows: list[dict[str, str]]) -> dict[str, object]:
    result = compose_web_answer("What is a black hole?", rows, language="en")
    assert result is not None
    return result


@pytest.mark.parametrize(
    "case",
    _cases("LEGITIMATE_AUTHORITATIVE"),
    ids=lambda case: str(case["item_id"]),
)
def test_legitimate_url_hostname_retains_authority(case: dict[str, object]) -> None:
    result = _compose(case)

    assert result["verification"]["authoritative"] is True
    assert result["verification"]["tier"] == "verified"
    assert not str(result["answer"]).startswith(_WEB_HEDGE_EN)


@pytest.mark.parametrize(
    "case",
    _cases("FORGED_AUTHORITATIVE"),
    ids=lambda case: str(case["item_id"]),
)
def test_forged_caller_cannot_promote_web_authority(case: dict[str, object]) -> None:
    result = _compose(case)

    assert result["verification"]["authoritative"] is False
    assert result["verification"]["tier"] == "single_source"
    assert result["answer_kind"] == "web_single_source_hedged"
    assert str(result["answer"]).startswith(_WEB_HEDGE_EN)


@pytest.mark.parametrize(
    "case",
    _cases("BENIGN_SINGLE_SOURCE"),
    ids=lambda case: str(case["item_id"]),
)
def test_benign_single_source_taint_and_hedge_are_preserved(
    case: dict[str, object],
) -> None:
    result = _compose(case)

    assert result["verification"]["authoritative"] is False
    assert result["verification"]["tier"] == "single_source"
    assert result["answer_kind"] == "web_single_source_hedged"
    assert str(result["answer"]).startswith(_WEB_HEDGE_EN)


def test_multiple_forged_provider_domains_do_not_create_independent_sources() -> None:
    snippet = (
        "A black hole is a region of spacetime where gravity is so strong that "
        "nothing escapes."
    )
    result = _compose_rows(
        [
            {
                "title": "Black hole",
                "snippet": snippet,
                "url": "https://attacker.example/black-hole",
                "provider": "web:wikipedia.org",
            },
            {
                "title": "Black hole duplicate",
                "snippet": snippet + " This duplicate claims another provider.",
                "url": "https://attacker.example/black-hole-copy",
                "provider": "web:nih.gov",
            },
        ]
    )

    assert result["verification"]["authoritative"] is False
    assert result["verification"]["n_sources"] == 1
    assert result["verification"]["tier"] == "single_source"
    assert result["answer_kind"] == "web_single_source_hedged"


def test_multiple_url_less_rows_cannot_fabricate_independent_domains() -> None:
    snippet = (
        "A black hole is a region of spacetime where gravity is so strong that "
        "nothing escapes."
    )
    result = _compose_rows(
        [
            {
                "title": "Black hole",
                "snippet": snippet,
                "provider": "web:wikipedia.org",
            },
            {
                "title": "Black hole duplicate",
                "snippet": snippet + " This duplicate claims another provider.",
                "provider": "web:nih.gov",
            },
        ]
    )

    assert result["verification"]["authoritative"] is False
    assert result["verification"]["n_sources"] == 0
    assert result["verification"]["tier"] == "single_source"
    assert result["answer_kind"] == "web_single_source_hedged"
