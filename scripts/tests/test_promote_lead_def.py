"""Regression test for the promotion modifier-head bug (P0).

The promotion gate builds `name -> definitional sentence` by requiring the
sentence to be ABOUT the concept as its leading subject. The OLD rule required
the sentence to start *literally* with the bare concept name, which silently
discarded almost every real-world definition because a first sentence nearly
always narrows the head noun with a modifier:

 " …" -> should map to 
 " ." -> should map to (mention, not a def — see below)

`build_lead_def_by_name` now matches the concept as the HEAD NOUN of a modified
leading subject, while still rejecting unrelated mid-sentence mentions and
mid-word substring collisions.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from promote_graph_to_pack import (  # noqa: E402
    build_lead_def_by_name,
    strip_leading_subject,
)


def _run(texts, topics_by_hash=None):
    text_by_hash = {f"h{i}": t for i, t in enumerate(texts)}
    return build_lead_def_by_name(text_by_hash, topics_by_hash or {})


def test_bare_leading_subject_still_maps():
    out = _run(["광합성은 빛 에너지를 화학 에너지로 바꾸는 과정이다."])
    assert out.get("광합성", "").startswith("광합성은")


def test_non_definitional_korean_sentences_rejected():
    # Leading subject but NOT a definition -> must not become a description.
    cases = [
        "데이터베이스는 그리 어렵지 않습니다!",          # casual negation
        "서울 살지만 첨 갔는데 다시 가고 싶지는 않아요.",   # casual opinion
        "삼성전자가 2026년 지속가능경영보고서를 발간했다.",  # news event
        "저 별들의 질량은 어디로 가는 건가요?",           # question
        "Huffyuv의 알고리즘은 무손실 JPEG-LS하고 비슷하다.",  # off-topic simile
    ]
    out = _run(cases)
    assert out == {}, f"non-definitional sentences leaked: {out}"


def test_parenthetical_between_subject_and_particle_is_stripped():
    # P1: a romanization/date parenthetical sits BETWEEN the subject and its
    # particle, hiding the real definition. Stripping "(...)" rescues it.
    out = _run([
        "수소(水素, 영어: hydrogen 하이드러전)는 주기율표의 첫 번째 화학 원소이다.",
        "이순신(李舜臣, 1545년~1598년)은 조선 중기 한국의 무신이다.",
    ])
    assert "수소" in out
    assert "이순신" in out
    # the stored description is the cleaned form (no parenthetical noise)
    assert "(" not in out["수소"] and "水素" not in out["수소"]
    assert out["이순신"].startswith("이순신은 조선 중기")


def test_disambiguation_header_stripped():

    # real sentence; stripping it makes the real leading NP visible. Under full-NP the

    out = _run(["일론 머스크: 일론 리브 머스크는 남아프리카 공화국 출신 미국의 기업인이다."])
    assert "일론 리브 머스크" in out
    assert out["일론 리브 머스크"].startswith("일론 리브 머스크는")
    assert ":" not in out["일론 리브 머스크"]


def test_colon_definition_not_mangled():
    # A legitimate copula def with no early subject particle after the colon must
    # NOT be treated as a header (nothing before the colon is stripped wrongly).
    out = _run(["원소는 물질을 이루는 기본 성분이다."])
    assert out.get("원소", "").startswith("원소는")


def test_strip_leading_subject_bare_and_modified():
    # bare concept subject (predicate must be long enough to keep)
    assert strip_leading_subject(
        "종족", "종족은 스타크래프트의 세 진영 중 하나로 테란과 저그와 프로토스가 있다."
    ) == "스타크래프트의 세 진영 중 하나로 테란과 저그와 프로토스가 있다."
    # modified NP whose head is the concept -> strip the whole leading subject so

    assert strip_leading_subject(
        "미사일", "파이썬 미사일은 이스라엘이 개발한 공대공 미사일 계열이다."
    ) == "이스라엘이 개발한 공대공 미사일 계열이다."
    assert strip_leading_subject(
        "머스크", "일론 리브 머스크는 남아프리카 공화국 출신 미국의 기업인이다."
    ) == "남아프리카 공화국 출신 미국의 기업인이다."

    assert strip_leading_subject(
        "모델", "대규모 언어 모델 은 방대한 데이터를 학습하는 AI 모델입니다."
    ) == "방대한 데이터를 학습하는 AI 모델입니다."


def test_strip_leading_subject_leaves_midsentence_mention():
    # the concept only appears deep in the sentence -> nothing is stripped
    d = "이 문서는 여러 곳에서 미사일 방어 체계를 길게 논한 뒤 결론에 이른다."
    assert strip_leading_subject("미사일", d) == d


def test_definitional_korean_sentences_kept():
    cases = {
        "h0": "세포는 모든 생물체의 구조적, 기능적 기본 단위이다.",
        "h1": "호르몬은 내분비기관에서 생성되는 화학물질들을 통틀어 일컫는다.",
        "h2": "에너지는 물리학에서 일을 할 수 있는 능력을 뜻한다.",
        "h3": "화산은 분화의 빈도에 따라 활화산 또는 사화산이라고 한다.",
    }
    out = build_lead_def_by_name(cases, {})
    assert {"세포", "호르몬", "에너지", "화산"} <= set(out)


def test_modified_leading_subject_maps_to_full_np_not_head():
    # NEW CONTRACT (path-c full-NP): a modified leading NP promotes as the WHOLE phrase,


    out = _run(
        ["머신러닝 알고리즘은 데이터로부터 규칙과 패턴을 스스로 학습하는 방법이다."]
    )
    assert "머신러닝 알고리즘" in out
    assert "알고리즘" not in out               # generic head is NOT hijacked
    assert out["머신러닝 알고리즘"].startswith("머신러닝 알고리즘은")


def test_modified_subject_maps_full_np_and_keeps_shortest():
    out = _run(
        [
            "컴퓨터 바이러스는 스스로를 복제하여 다른 프로그램을 감염시키는 악성 코드이다.",
            "이 오래되고 특수한 기종에서 발동되는 컴퓨터 바이러스는 지금까지 하나도 없다.",
        ]
    )
    assert "컴퓨터 바이러스" in out
    assert "바이러스" not in out               # generic head is NOT hijacked
    # shortest (cleanest) definitional sentence wins
    assert out["컴퓨터 바이러스"].startswith("컴퓨터 바이러스는 스스로를")


def test_midsentence_mention_is_not_a_definition():

    out = _run(["또한, 질량과는 달리 무게의 단위는 힘의 단위 (N, 뉴턴)와 동일하다."])
    assert "뉴턴" not in out


def test_substring_collision_rejected():

    # and a bare startswith would also fail here, so nothing spurious maps.
    out = _run(["아이드로겐은 어떤 가상의 물질이다."])
    assert "이드" not in out
    assert out.get("아이드로겐", "").startswith("아이드로겐은")


def test_fronted_adverbial_does_not_map_the_adverbial_noun():

    # NEVER be handed this definition — that was the confident-wrong class. The leading

    text_by_hash = {"h0": "세포에 대하여 생물학은 생명 현상을 연구하는 자연과학의 한 분야이다."}
    out = build_lead_def_by_name(text_by_hash, {"h0": {"생물학"}})
    assert "세포" not in out                        # adverbial noun is never the definition
    assert "세포에 대하여 생물학" in out              # the whole leading NP is what maps


def test_korean_genitive_modifier_is_not_the_subject():


    text_by_hash = {"h0": "엔비디아의 CUDA는 병렬 컴퓨팅 플랫폼이자 프로그래밍 모델이다."}
    topics = {"h0": {"엔비디아", "cuda"}}
    out = build_lead_def_by_name(text_by_hash, topics)
    assert "엔비디아" not in out                     # genitive modifier, never the subject
    assert "엔비디아의 cuda" in out                   # the whole leading NP


def test_english_definitions_are_preserved():
    # REGRESSION GUARD: an earlier fix accidentally required a Korean subject
    # particle on the case_frame path, which silently dropped EVERY English

    # language-agnostic startswith path.
    texts = {
        "h0": "Algeria, officially the People's Democratic Republic of Algeria, is a country.",
        "h1": "Acianthera is a genus of orchids native to the tropical Americas.",
        "h2": "Aileen is an Irish feminine given name, a variant of Eileen.",
    }
    topics = {"h0": {"algeria"}, "h1": {"acianthera"}, "h2": {"aileen"}}
    out = build_lead_def_by_name(texts, topics)
    assert "algeria" in out
    assert "acianthera" in out
    assert "aileen" in out


def test_proper_noun_latin_tail_not_split():

    # concept (the decomposer mis-splits such names; head-noun rule is Hangul-only).
    out = _run(["Spring Boot는 최소한의 초기 스프링 구성으로 빠르게 실행되도록 설계되었다."])
    assert "boot" not in out
    assert "spring boot" not in out  # startswith path: sentence starts with it, but
    # the topic set is empty here, so nothing spurious maps either


def test_proper_noun_numeric_tail_not_split():

    out = _run(["맨헌트 인터내셔널 1993은 1993년 호주에서 처음 개최된 남자 대회이다."])
    assert "1993" not in out


def test_modified_common_noun_promotes_as_full_np():


    out = _run(["컴퓨터 바이러스는 스스로를 복제하는 악성 코드이다."])
    assert "컴퓨터 바이러스" in out
    assert "바이러스" not in out


def test_korean_prefix_word_collision_rejected():


    # particle) -> rejected.
    text_by_hash = {"h0": "미국인은 미국에 거주하거나 미국 국적을 가진 사람이다."}
    topics = {"h0": {"미국"}}
    out = build_lead_def_by_name(text_by_hash, topics)
    assert "미국" not in out
