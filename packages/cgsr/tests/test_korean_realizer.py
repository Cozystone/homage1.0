from __future__ import annotations

from cgsr.korean_realizer import attach_eomi, realize_simple_clause, select_eomi, select_euro_ro, select_josa


def test_select_josa_for_final_and_open_syllables() -> None:
    final_words = ["책", "밥", "집", "문맥", "값", "앱", "꽃", "길", "지식", "GraphRAG"]
    open_words = ["나무", "학교", "쿠버네티스", "데이터", "노드", "그래프", "아카이브", "토폴로지", "AI", "CPU"]

    assert select_josa("책", ("은", "는")) == "은"
    assert select_josa("나무", ("은", "는")) == "는"
    assert all(select_josa(word, ("이", "가")) == "이" for word in final_words)
    assert all(select_josa(word, ("을", "를")) == "를" for word in open_words)


def test_latin_acronym_josa_policy() -> None:
    final_like = ["GraphRAG", "LLM", "JSON", "R"]
    open_like = ["AI", "CPU", "Kubernetes", "Docker", "Express", "Rust", "API-Gateway"]

    assert all(select_josa(word, ("은", "는")) == "은" for word in final_like)
    assert all(select_josa(word, ("은", "는")) == "는" for word in open_like)


def test_select_euro_ro_rieul_exception() -> None:

    assert select_euro_ro("나무") == "로"     # vowel-final
    assert select_euro_ro("서울") == "로"
    assert select_euro_ro("칼") == "로"
    assert select_euro_ro("손") == "으로"
    assert select_euro_ro("밥") == "으로"
    assert select_euro_ro("천재") == "로"     # vowel-final

    assert select_josa("서울", ("으로", "로")) == "로"
    assert select_josa("석학", ("으로", "로")) == "으로"


def test_realize_alryeojida_uses_euro_ro_allomorph() -> None:

    assert realize_simple_clause({"concept": "그", "predicate": "알려지다", "object": "서울"}) == "그는 서울로 알려집니다."
    assert realize_simple_clause({"concept": "그", "predicate": "알려지다", "object": "석학"}) == "그는 석학으로 알려집니다."


def test_select_eomi_minimal_patterns() -> None:
    assert select_eomi("하", "formal") == "합니다"
    assert select_eomi("하", "polite") == "해요"
    assert select_eomi("먹", "formal") == "습니다"


def test_attach_eomi_common_irregulars() -> None:
    assert attach_eomi("보여주", "formal") == "보여줍니다"
    assert attach_eomi("살", "formal") == "삽니다"
    assert attach_eomi("만들", "formal") == "만듭니다"
    assert attach_eomi("돕", "polite") == "도와요"
    assert attach_eomi("그렇", "polite") == "그래요"
    assert attach_eomi("듣", "polite") == "들어요"


def test_realize_simple_clause() -> None:
    sentence = realize_simple_clause({"concept": "쿠버네티스", "predicate": "관리한다", "object": "컨테이너"})

    assert sentence == "쿠버네티스는 컨테이너를 관리합니다."


def test_realize_show_bug_regression() -> None:
    sentence = realize_simple_clause({"concept": "아틀라스", "predicate": "보여준다", "object": "지역 신호와 상태"})

    assert sentence == "아틀라스는 지역 신호와 상태를 보여줍니다."


def test_realize_numeric_age_with_bound_expression() -> None:
    sentence = realize_simple_clause({"concept": "카터", "predicate": "살다", "object": "100"})

    assert sentence == "카터는 100세까지 삽니다."


def test_realize_intransitive_location_case() -> None:
    sentence = realize_simple_clause({"concept": "카터", "predicate": "태어나다", "object": "조지아주"})

    assert sentence == "카터는 조지아주에서 태어납니다."


def test_realize_response_predicate_uses_adverbial_case() -> None:
    sentence = realize_simple_clause({"concept": "아프가니스탄", "predicate": "대응한다", "object": "침공"})

    assert sentence == "아프가니스탄은 침공에 대응합니다."


def test_realize_four_digit_object_as_year_adverbial() -> None:
    sentence = realize_simple_clause({"concept": "케네디", "predicate": "물리치다", "object": "1980"})

    assert sentence == "케네디는 1980년에 물리칩니다."
