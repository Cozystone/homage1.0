"""Regression test for the pack_purity noise-relation detector (precision gate).

The detector removes the name↔definition mismatch stratum — the measured seed is
canonical_name "" whose definition is " 2023-24 " and whose
relations are scrape verbs ( ). The whole risk is over-quarantine: the engine
legitimately learns Korean verb predicates ( , ),
so a NON-structural Korean verb predicate alone must NEVER be enough to flag a concept.
Only the four-conjunct gate (non-battery + noise predicate + schedule/roster definition +
name-not-in-definition) may fire. These tests pin that gate so a future loosening trips.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from pack_purity import _is_noise_predicate, _is_noise_relation  # noqa: E402


def _concept(name: str, desc: str, rels: list[tuple[str, str]]) -> dict:
    return {
        "concept_id": "vsc_test",
        "canonical_name": name,
        "short_description": desc,
        "relations": [{"relation": r, "target": t} for r, t in rels],
    }


# ── _is_noise_predicate ──────────────────────────────────────────────────────

def test_scrape_verb_is_noise_predicate():
    assert _is_noise_predicate("죽다")
    assert _is_noise_predicate("맵다")
    assert _is_noise_predicate("작렬하다")


def test_structural_and_legit_predicates_are_not_noise():
    for p in ("is_a", "part_of", "used_for", "contrasts_with"):
        assert not _is_noise_predicate(p)

    for p in ("구성하다", "위치하다", "자리하다", "이루어지다", "의하다"):
        assert not _is_noise_predicate(p)


# ── _is_noise_relation — the four-conjunct gate ──────────────────────────────

def test_measured_seed_is_flagged():
    """ → + : the exact garbage that surfaced on ' '."""
    c = _concept("다음", "라리가 2023-24 경기 일정이다.",
                 [("is_a", "기록"), ("is_a", "차이점"), ("죽다", "모래")])
    flagged, reason = _is_noise_relation(c)
    assert flagged and reason == "noise-relation"


def test_noise_predicate_alone_does_not_flag():
    """The precision crux: a non-structural learned verb predicate with a COHERENT
    definition (not a roster fragment) must be kept — this is legit learning."""
    c = _concept("광합성반응", "빛 에너지를 화학 에너지로 바꾸는 과정이다.",
                 [("전환하다", "에너지"), ("이루어지다", "단계")])
    flagged, reason = _is_noise_relation(c)
    assert not flagged and reason == "desc-not-roster-fragment"


def test_locative_learned_concept_is_kept():
    """-shape: locative predicates + a definition that matches the name."""
    c = _concept("군량리", "양화천 서쪽 평야에 자리한 농촌마을이다.",
                 [("자리하다", "평야"), ("위치하다", "지역")])
    flagged, reason = _is_noise_relation(c)
    assert not flagged and reason == "no-noise-predicate"


def test_battery_floor_concept_is_never_flagged():
    """ carries scrape relations () but its definition is correct and it
 is a battery subject — the floor spares it regardless of its noisy relations."""
    c = _concept("대한민국", "동아시아 한반도 남부에 위치한 나라이다.",
                 [("작렬하다", "전반"), ("작렬하다", "선수")])
    flagged, reason = _is_noise_relation(c)
    assert not flagged and reason == "battery-floor"


def test_schedule_owner_is_kept():
    """A concept literally named for the schedule owns that fragment — name-in-desc spares it."""
    c = _concept("라리가", "라리가 2023-24 경기 일정이다.", [("죽다", "모래")])
    flagged, reason = _is_noise_relation(c)
    assert not flagged and reason == "name-owns-fragment"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
