# -*- coding: utf-8 -*-
from packages.base_brain import discourse_learner as dl


_REAL = [
    "엔비디아 코퍼레이션은 캘리포니아주 샌타클래라에 본사를 둔 미국의 다국적 기술 회사이다.",
    "이 회사는 소비자 가전, 소프트웨어, 서비스로 가장 잘 알려져 있다.",
    "1976년 스티브 잡스와 워즈니악이 애플을 설립했으며, 이듬해 법인으로 전환했다.",
    "2007년에는 초점을 소비자 가전으로 확대하면서 이름을 애플 주식회사로 바꾸었다.",
    "그 뒤 회사는 아이폰을 출시하여 시장을 크게 바꾸었다.",
    "이러한 변화는 업계 전체에 영향을 주었다.",
    "삼성전자는 대한민국의 대표적인 전자 기업으로 반도체와 스마트폰을 만든다.",
    "이 기업은 세계 여러 나라에 생산 시설을 두고 있으며, 연구에도 크게 투자한다.",
    "구글은 검색 서비스로 시작하여 다양한 분야로 사업을 넓혀 왔다.",
    "그 결과 오늘날에는 인공지능 연구에서도 앞서 나가고 있다.",
    "테슬라는 전기차를 만들면서 자동차 산업의 흐름을 바꾸어 놓았다.",
    "이러한 기업들은 서로 경쟁하며 기술을 빠르게 발전시켜 왔다.",
]


def test_learns_flow_stats_from_real_prose(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "_PROFILE", tmp_path / "profile.json")
    dl._CACHE["p"] = None
    p = dl.learn(_REAL)
    assert p["n_sentences"] == len(_REAL)

    # signals our list-y realizer lacks; the learner must measure them > 0.
    assert p["subordination_rate"] > 0
    assert p["reference_rate"] > 0
    assert p["top_endings"]  # ending distribution learned


def test_prefers_flowing_prose_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "_PROFILE", tmp_path / "profile.json")
    dl._CACHE["p"] = None
    dl.learn(_REAL * 6)  # enough evidence
    assert dl.prefers_flowing_prose() is True
    # empty profile → no opinion (never forces the style change without evidence)
    monkeypatch.setattr(dl, "_PROFILE", tmp_path / "absent.json")
    dl._CACHE["p"] = None
    assert dl.prefers_flowing_prose() is False
