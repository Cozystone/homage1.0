"""Root-cause guard: a person-bio subject must not extract the birthdate unit '' as its head."""
from __future__ import annotations

from cgsr.induction import _argument_head


def test_bio_subject_extracts_name_not_birthdate_unit():

    assert _argument_head("홍길동(洪吉童, 1992년 8월 28일 ~ )") == "홍길동"
    assert _argument_head("김철수(1980년 ~ )") == "김철수"


def test_bare_date_argument_yields_no_head():
    assert _argument_head("1992년 8월 28일") == ""
    assert _argument_head("28일") == ""
    assert _argument_head("2021년") == ""


def test_normal_arguments_unchanged():
    assert _argument_head("대한민국의 축구 선수") == "선수"
    assert _argument_head("빠른 갈색 여우") == "여우"
    assert _argument_head("컴퓨터") == "컴퓨터"
