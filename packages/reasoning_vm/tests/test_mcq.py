# -*- coding: utf-8 -*-
"""Free-text MCQ parsing + verify-gated answering (the deployed AI crushes a pasted 4)."""
from packages.reasoning_vm.mcq import parse_mcq, answer_mcq

_KG = {
    "프랑스": [("프랑스", "capital", "파리")],
    "고래": [("고래", "is_a", "포유류")],
    "포유류": [("포유류", "is_a", "동물")],
}


def _fa(subject):
    return _KG.get(subject, [])


# ── parsing surface formats ───────────────────────────────────────────────────────────────────
def test_parse_circled():
    r = parse_mcq("프랑스의 수도는? ① 런던 ② 파리 ③ 베를린 ④ 로마")
    assert r is not None
    stem, choices, labels = r
    assert stem.startswith("프랑스의 수도")
    assert choices == {"A": "런던", "B": "파리", "C": "베를린", "D": "로마"}
    assert labels["B"] == "②"


def test_parse_numbered_newlines():
    r = parse_mcq("다음 중 프랑스의 수도는?\n1. 런던\n2. 파리\n3. 베를린\n4. 로마")
    assert r is not None and r[1]["B"] == "파리"


def test_parse_alpha_paren():
    r = parse_mcq("Capital of France?  A) London  B) Paris  C) Berlin  D) Rome")
    assert r is not None and r[1]["B"] == "Paris"


def test_non_mcq_returns_none():
    assert parse_mcq("프랑스의 수도가 어디야?") is None
    assert parse_mcq("나는 어제 사과 3개를 먹었다.") is None    # a stray '3' must not trigger


# ── end-to-end answering (verify-gated) ───────────────────────────────────────────────────────
def test_answer_factual_mcq():
    r = answer_mcq("프랑스의 수도는? ① 런던 ② 파리 ③ 베를린 ④ 로마", _fa)
    assert r and r["status"] == "GROUNDED"
    assert r["choice_key"] == "B" and r["choice_label"] == "②" and r["answer_text"] == "파리"


def test_answer_abstains_when_uncovered():
    r = answer_mcq("힉스 입자의 스핀은? ① 0 ② 1/2 ③ 1 ④ 2", _fa)
    assert r and r["status"] == "ABSTAIN" and r["choice_key"] is None


def test_answer_none_when_not_mcq():
    assert answer_mcq("그냥 잡담이야", _fa) is None
