"""Plan-then-realize: definition first, zero-subject anaphora, inspectable plan."""
from __future__ import annotations

from cgsr.discourse_planner import plan_and_realize


FACTS = [
    ("USED_FOR", "그래픽 처리"),
    ("IS_A", "반도체 기업"),
    ("LOCATED_IN", "샌타클래라"),
    ("HAS_PART", "GPU 사업부"),
]


def test_definition_comes_first_regardless_of_input_order():
    para = plan_and_realize("엔비디아", FACTS)
    assert para.plan[0] == "DEFINE"
    assert para.sentences[0].text.startswith("엔비디아는 반도체 기업의 한 종류입니다.")


def test_zero_subject_anaphora_after_first_sentence():
    para = plan_and_realize("엔비디아", FACTS)
    # the topic is named exactly once — repeating it every sentence is machine-text
    assert para.text.count("엔비디아") == 1
    assert len(para.sentences) >= 3


def test_connectives_rotate_between_moves():
    para = plan_and_realize("엔비디아", FACTS)
    later = " ".join(s.text for s in para.sentences[1:])
    assert any(c in later for c in ("또한", "그리고", "한편"))


def test_plan_is_the_derivation_trace():
    para = plan_and_realize("엔비디아", FACTS)
    d = para.to_dict()
    # every sentence points at the facts it realizes — XAI contract
    assert all(s["facts"] for s in d["sentences"])
    assert ["DEFINE"] == d["plan"][:1]


def test_topic_without_definition_still_opens_with_topic():
    para = plan_and_realize("쿠버네티스", [("USED_FOR", "컨테이너 오케스트레이션")])
    assert para.sentences[0].text.startswith("쿠버네티스는 ")
    assert "컨테이너 오케스트레이션" in para.text


def test_josa_agrees_with_batchim():
    para = plan_and_realize("서울", [("IS_A", "도시"), ("LOCATED_IN", "한반도")])
    assert para.sentences[0].text.startswith("서울은 ")
