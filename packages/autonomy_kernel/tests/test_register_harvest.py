# -*- coding: utf-8 -*-
"""L1 multi-register harvest: routing, safety floors, consensus coverage, active-learning target."""
import importlib

import pytest

rh = importlib.import_module("packages.autonomy_kernel.register_harvest")


@pytest.fixture()
def bank(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_BANK", tmp_path / "reg.jsonl")
    return tmp_path


ROUTES = [
    ("정말 힘드셨겠어요 곁에서 응원할게요", "comfort"),
    ("축하해요 정말 잘됐네요 대단해요", "celebrate"),
    ("한 번 이렇게 해 보세요 도움이 될 거예요", "advice"),
    ("왜냐하면 그 방식이 안정적이기 때문이에요", "explain"),
    ("제 생각엔 그게 더 나은 선택인 것 같아요", "opinion"),
    ("그건 어떻게 시작하면 좋을까요", "question"),
    ("ㅋㅋ 그러게요 완전 웃기네요", "banter"),
]


@pytest.mark.parametrize("frag,expected", ROUTES)
def test_routing(frag, expected):
    assert rh._route_register(frag) == expected


def test_question_shape_beats_advice():

    assert rh._route_register("어떻게 하면 좋을까요") == "question"


def test_safety_floor_blocks_medical_financial(bank):
    txt = "약 드시는 걸 추천해요. 이 주식 사는 걸 추천드려요. 제 생각엔 코인 투자가 답인 것 같아요."
    rep = rh.harvest_register(txt, "https://x.com")
    # every fragment is directive/stance about a risky topic → nothing banked
    assert rep["harvested"] == 0
    assert rep["rejected"] >= 1


def test_consensus_coverage_and_thinnest(bank):
    txt = ("정말 힘내세요 응원할게요. 축하해요 너무 잘됐어요. 한 번 해 보세요 좋을 거예요. "
           "왜냐하면 그게 더 안정적이기 때문이에요. 제 생각엔 그게 맞는 것 같아요. "
           "그건 어떻게 하면 좋을까요. ㅋㅋ 그러게요 완전 웃기네요.")
    rh.harvest_register(txt, "https://siteA.com")     # domain 1
    cov1 = rh.register_coverage()
    assert cov1["total_usable"] == 0                   # 1 domain < MIN_DOMAINS, nothing usable yet
    rh.harvest_register(txt, "https://siteB.com")      # domain 2 → consensus
    cov2 = rh.register_coverage()["usable"]
    assert all(cov2[r] >= 1 for r in ("comfort", "celebrate", "advice", "explain", "opinion", "question", "banter"))
    # after uniform coverage, thinnest is well-defined (no crash, returns k registers)
    assert len(rh.thinnest_registers(3)) == 3


def test_privacy_anonymized(bank):
    # a handle + phone number in a comfort line must be scrubbed before banking.
    # (page text must be >= 40 chars — the whole-page intake floor — so pad with real register.)
    page = ("영희님 010-1234-5678 정말 힘내세요 응원할게요. "
            "오늘 하루도 정말 고생 많으셨어요 곁에서 늘 응원할게요.")
    rh.harvest_register(page, "https://a.com")
    rh.harvest_register(page, "https://b.com")
    import json
    banked = [json.loads(l) for l in rh._BANK.read_text(encoding="utf-8").splitlines()]
    assert banked, "expected at least one banked fragment"
    for row in banked:
        assert "010" not in row["pattern"] and "1234" not in row["pattern"]
        assert "영희" not in row["pattern"]     # addressed name neutralized
