"""Regression suite for compose_web_answer — the extractive web-answer composer.

Locks in the answer-quality fixes made while hardening the demo Q&A:
 - key-term COVERAGE guard: an off-topic page (shares a word, misses another) abstains
 instead of pasting a wrong-referent definition ("What is a black hole?" must not answer
 "Black is a color…");
 - question-type-aware LEAD (subject_lead): WHO picks the person (entity is the HEAD noun),
 WHAT picks the entity that HEADS the phrase — so " ?" → the physicist not
 " ", and " ?" → the company not " ";
 - RICHNESS: same-source continuation sentences (pronoun/ellipsis) join the answer;
 - cross-referent supporting facts are dropped from the body;
 - FOLLOW-UPS: related-page titles, excluding the entity's own page and a homonym's.

Pure-function tests — no app fixtures, no network.
"""
from __future__ import annotations

import pathlib
import sys

# compose_web_answer imports packages.cgsr.cgsr.referent_resonance; make the repo root
# importable so that `packages` resolves (mirrors the app runtime whose cwd is the repo root).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.web_search import compose_web_answer


def _rows(*pairs):
    return [{"snippet": snip, "title": title} for title, snip in pairs]


def _answer(query, rows, language="ko"):
    result = compose_web_answer(query, rows, language=language)
    return (result or {}).get("answer")


# --- coverage guard: off-topic page abstains --------------------------------------------

def test_offtopic_page_abstains():
    # "Black" (the color) shares 'black' with the query but not 'hole' → must abstain.
    rows = _rows(("Black", "Black is a color that results from the absence of visible light."))
    assert compose_web_answer("What is a black hole?", rows, language="en") is None


def test_on_topic_black_hole_answers():
    rows = _rows(("Black hole", "A black hole is a region of spacetime where gravity is so strong that nothing escapes."))
    ans = _answer("What is a black hole?", rows, language="en")
    assert ans and "black hole" in ans.lower()


def test_black_hole_with_offtopic_color_present_drops_the_color():
    rows = _rows(
        ("Black hole", "A black hole is a region of spacetime where gravity is so strong nothing escapes. It forms from a collapsing star."),
        ("Black", "Black is a color that results from the absence of visible light."),
    )
    ans = _answer("What is a black hole?", rows, language="en")
    assert ans and ans.startswith("A black hole")
    assert "is a color" not in ans  # off-topic referent must not leak into the body


# --- question-type-aware lead -----------------------------------------------------------

def test_who_query_picks_person_not_derived_compound():
    rows = _rows(
        ("아인슈타인 방정식", "아인슈타인 방정식(Einstein方程式)은 일반 상대성이론의 중력장 방정식이다."),
        ("알베르트 아인슈타인", "알베르트 아인슈타인(1879년~1955년)은 독일 태생의 이론물리학자이다."),
    )
    ans = _answer("아인슈타인이 누구야?", rows)
    assert ans and ans.startswith("알베르트 아인슈타인")


def test_what_query_disambiguates_homonym_to_the_company():
    rows = _rows(
        ("니콜라 테슬라", "니콜라 테슬라(1856년~1943년)는 세르비아계 미국인 발명가이다."),
        ("테슬라", "테슬라(Tesla, Inc.)는 미국의 전기자동차 회사이다."),
    )
    ans = _answer("테슬라가 뭐야?", rows)
    assert ans and ans.startswith("테슬라")
    assert "발명가" not in ans  # the person referent must not leak into the body


def test_what_query_prefers_entity_headed_over_object_mention():
    rows = _rows(
        ("CUDA", "CUDA는 엔비디아가 2006년에 만들었다."),
        ("엔비디아", "엔비디아 코퍼레이션(Nvidia Corporation)은 미국의 다국적 기업이자 기술 회사이다."),
    )
    ans = _answer("엔비디아가 뭐야?", rows)
    assert ans and ans.startswith("엔비디아 코퍼레이션")


# --- richness: same-source continuations ------------------------------------------------

def test_rich_answer_keeps_paragraph_continuations():
    snip = (
        "손흥민(孫興慜, 1992년~)은 대한민국의 축구 선수로, 포지션은 공격수이다. "
        "현재 로스앤젤레스 FC 소속이며 대한민국 국가대표팀 주장이다. "
        "프리미어리그 역대 아시아 선수 최다 득점자이다."
    )
    ans = _answer("손흥민이 누구야?", _rows(("손흥민", snip)))
    assert ans
    assert "공격수" in ans and "주장" in ans and "득점자" in ans  # >1 fact, not a one-liner


# --- follow-ups -------------------------------------------------------------------------

def test_follow_ups_are_related_titles_excluding_entity_and_homonym():
    rows = _rows(
        ("손흥민", "손흥민은 대한민국의 축구 선수로 공격수이다."),
        ("대한민국 축구 국가대표팀", "대한민국 축구 국가대표팀은 FIFA 월드컵에 출전한다."),
        ("프리미어리그", "프리미어리그는 잉글랜드 최상위 축구 리그이다."),
    )
    result = compose_web_answer("손흥민이 누구야?", rows)
    fu = (result or {}).get("follow_ups") or []
    assert "대한민국 축구 국가대표팀" in fu and "프리미어리그" in fu
    assert all("손흥민" not in f for f in fu)  # the entity's own page is not a follow-up


def test_follow_ups_exclude_homonym_page():
    rows = _rows(
        ("테슬라", "테슬라(Tesla, Inc.)는 미국의 전기자동차 회사이다."),
        ("니콜라 테슬라", "니콜라 테슬라는 발명가이다."),
        ("일론 머스크", "일론 머스크는 테슬라의 CEO이다."),
    )
    result = compose_web_answer("테슬라가 뭐야?", rows)
    fu = (result or {}).get("follow_ups") or []
    assert all("테슬라" not in f for f in fu)  # own page + homonym excluded
    assert "일론 머스크" in fu
