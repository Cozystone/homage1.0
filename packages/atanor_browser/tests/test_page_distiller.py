# -*- coding: utf-8 -*-
"""Page distiller — the browser's honest DOM->graph gate."""

from __future__ import annotations

from packages.atanor_browser import distill_page

_PAGE = """
<html><head><title>팔란티어 - 위키백과</title></head><body>
<nav><a href="/">홈</a> | <a href="/a">뉴스</a> | <a href="/b">로그인</a></nav>
<article>
<p>팔란티어는 빅데이터 분석을 전문으로 하는 미국의 소프트웨어 기업이다.</p>
<p>팔란티어 테크놀로지스는 2003년에 설립되었다.</p>
<p>미라큘러스는 프랑스의 애니메이션이다.</p>
</article>
<footer>쿠키 정책 | 개인정보처리방침 | 회사소개</footer>
</body></html>
"""


def test_title_anchor_and_copula_extraction():
    out = distill_page(_PAGE, url="https://ko.wikipedia.org/wiki/팔란티어")
    assert out["anchor"] == "팔란티어"
    assert len(out["triples"]) == 1
    t = out["triples"][0]
    assert t["subject"] == "팔란티어" and t["predicate"] == "defined_as"
    assert "소프트웨어 기업" in t["object"]
    assert t["url"].endswith("팔란티어")  # provenance always


def test_off_anchor_sentence_never_becomes_a_triple():
    out = distill_page(_PAGE)


    assert all("미라큘러스" not in t["object"] for t in out["triples"])
    assert out["dropped"]["off_anchor"] >= 1


def test_boilerplate_and_nav_never_reach_extraction():
    out = distill_page(_PAGE)
    joined = " ".join(t["object"] for t in out["triples"])
    joined += " ".join(e["sentence"] for e in out["evidence"])
    assert "로그인" not in joined and "쿠키 정책" not in joined


def test_anchor_relevant_prose_lands_as_evidence():
    out = distill_page(_PAGE)
    assert any("2003년에 설립" in e["sentence"] for e in out["evidence"])


def test_never_writes_and_survives_garbage():
    assert distill_page(_PAGE)["written_to_store"] is False
    out = distill_page("<<<<not html at all")
    assert out["triples"] == []  # graceful, never raises
