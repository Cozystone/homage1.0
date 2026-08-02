# -*- coding: utf-8 -*-
""" (B1 contrast / B2 purpose) — same GCG closure contract as v1:
every content span is a verbatim stored label; connectives come from a closed
whitelist; inherited facts must NAME their taxonomy source in the sentence."""
from __future__ import annotations

from packages.grounded_composer.composer import (
    compose_comparison,
    compose_purpose,
)


def test_contrast_two_subjects_with_commonality():
    fa = [("커피", "defined_as", "볶은 원두로 내린 음료")]
    fb = [("차", "defined_as", "찻잎을 우린 음료")]
    common = ("음료", [("커피", "is_a", "음료")], [("차", "is_a", "음료")])
    r = compose_comparison("커피", "차", fa, fb, common)
    assert r is not None
    assert "커피는 볶은 원두로 내린 음료입니다." in r.answer
    assert "반면 차는 찻잎을 우린 음료입니다." in r.answer
    assert "둘 다 음료의 일종이라는 공통점이 있습니다." in r.answer
    # the taxonomy edges that ground the commonality are cited in the certificate
    assert ("커피", "is_a", "음료") in r.facts_used
    assert ("차", "is_a", "음료") in r.facts_used


def test_contrast_without_commonality_still_contrasts():
    fa = [("커피", "is_a", "음료")]
    fb = [("서울", "located_in", "한국")]
    r = compose_comparison("커피", "서울", fa, fb, None)
    assert r is not None
    assert "반면" in r.answer
    assert "공통점" not in r.answer


def test_contrast_never_contrasts_identical_facts():
    # both subjects share the exact same lead fact — the pick must differ or the
    # contrast is vacuous; with only identical facts available the 2nd pick falls
    # back and the sentence still names both subjects verbatim
    fa = [("A", "is_a", "동물")]
    fb = [("B", "is_a", "동물"), ("B", "located_in", "동물원")]
    r = compose_comparison("A", "B", fa, fb, None)
    assert r is not None
    assert "B는 동물원에 있" in r.answer or "동물원" in r.answer


def test_contrast_vocabulary_closed():
    fa = [("커피", "defined_as", "음료")]
    fb = [("차", "defined_as", "찻잎 음료")]
    r = compose_comparison("커피", "차", fa, fb, None)
    # strip source tag, then longest fact strings first, then template constants;
    # nothing may remain — that IS the closed-vocabulary property
    rest = r.answer.replace("(출처: 큐레이션 지식그래프)", "")
    for token in sorted(("커피", "차", "음료", "찻잎 음료"), key=len, reverse=True):
        rest = rest.replace(token, "")
    for tpl in ("는", "은", "입니다", "반면", ".", " "):
        rest = rest.replace(tpl, "")
    assert rest.strip() == "", f"unexpected tokens: {rest!r}"


def test_purpose_direct_facts_lead():
    direct = [("망치", "used_for", "못 박기"), ("망치", "capable_of", "부수기")]
    r = compose_purpose("망치", direct)
    assert r is not None
    assert r.answer.startswith("망치는 못 박기에 쓰입니다.")
    assert "또한 '부수기'" in r.answer


def test_purpose_inherited_names_its_source():

    inherited = [([("참새", "is_a", "새")], ("새", "capable_of", "날다"))]
    r = compose_purpose("참새", [], inherited)
    assert r is not None
    assert "새의 일종으로서" in r.answer
    assert "'날다'" in r.answer
    assert ("참새", "is_a", "새") in r.facts_used


def test_purpose_nothing_stored_stays_silent():
    assert compose_purpose("무근거개념", [], []) is None


def test_purpose_dedupes_inherited_duplicates_of_direct():
    direct = [("망치", "used_for", "못 박기")]
    inherited = [([("망치", "is_a", "도구")], ("도구", "used_for", "못 박기"))]
    r = compose_purpose("망치", direct, inherited)
    assert r is not None
    assert r.answer.count("못 박기") == 1
