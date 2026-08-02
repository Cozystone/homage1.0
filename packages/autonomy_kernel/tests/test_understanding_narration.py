# -*- coding: utf-8 -*-
"""Understanding narration (owner 2026-07-10): the orb narrates the READING process the way a
person would — every clause measured (URL topic, page concept frequency, graph-derived
self-neighborhood), polite register, never authored prose."""
from packages.autonomy_kernel import activity_feed as af
from packages.autonomy_kernel import web_expedition as we


def test_topic_from_url_reads_wiki_subject():
    assert we._topic_from_url("https://ko.wikipedia.org/wiki/%EA%B0%80%EC%83%81_%EB%A8%B8%EC%8B%A0") == "가상 머신"
    assert we._topic_from_url("https://namu.wiki/w/%EC%BB%A4%ED%94%BC") == "커피"
    assert we._topic_from_url("https://news.ycombinator.com/") == "news.ycombinator.com"


def test_top_concepts_measures_frequency():
    sents = ["가상머신은 소프트웨어 환경이다"] * 3 + ["가상머신 격리 격리 이야기"]
    top = we._top_concepts(sents)
    assert top and top[0] == "가상머신"


def test_understand_voice_or_telemetry_never_molds(monkeypatch):
    """New contract (owner 2026-07-11: — ):
 _understand returns either a GENERATED line or a clearly-marked [] telemetry readout.
 Asserted here with generation forced off: the telemetry tiers carry the measured self-link
 (core marker iff the graph core connects, marker for lived-only, none otherwise) and no
 pretend-understanding prose survives."""
    import packages.continuous_self.thought_language as tl
    monkeypatch.setattr(tl, "realize_thought", lambda *a, **k: None)   # force the telemetry tier
    # tier 1: GRAPH atanor-neighborhood hit → the core marker is licensed
    monkeypatch.setattr(we, "_self_neighborhood", lambda: {"core": {"가상머신"}, "lived": set()})
    line, hit = we._understand("가상 머신", ["가상머신", "격리"])
    assert hit == "가상머신"
    assert line.startswith("[실측]") and "자기연결(core): 가상머신" in line

    # tier 2: only the LIVED narrative connects → never the core marker
    monkeypatch.setattr(we, "_self_neighborhood", lambda: {"core": set(), "lived": {"격리"}})
    line_l, hit_l = we._understand("가상 머신", ["격리"])
    assert hit_l == "격리" and "자기연결(core)" not in line_l and "자기연결(서사): 격리" in line_l

    # no connection anywhere → no self-claim and no pretend-understanding phrasing
    monkeypatch.setattr(we, "_self_neighborhood", lambda: {"core": set(), "lived": set()})
    line2, hit2 = we._understand("커피", ["카페인"])
    assert hit2 is None and line2.startswith("[실측]")
    assert "자기연결" not in line2 and "이해해 보는 중" not in line2 and "언저리" not in line2


def test_ingest_page_journals_understanding(tmp_path, monkeypatch):
    monkeypatch.setattr(we, "_JOURNAL", tmp_path / "exp.jsonl")
    monkeypatch.setattr(we, "_self_neighborhood", lambda: {"core": set(), "lived": set()})
    from packages.autonomy_kernel import narrative_corpus as nc
    monkeypatch.setattr(nc, "CORPUS", tmp_path / "corpus.jsonl")   # don't touch the real store
    text = "가상머신은 물리 컴퓨터를 흉내 내는 실행 환경이다. " * 6
    rep = we.ingest_page("https://ko.wikipedia.org/wiki/%EA%B0%80%EC%83%81_%EB%A8%B8%EC%8B%A0", text)
    assert rep["understanding"] and rep["topic"] == "가상 머신"
    assert not rep["injection_blocked"]


def test_feed_ticker_is_instrumentation_not_speech():
    """New contract (owner 2026-07-11): the always-on channel is an INSTRUMENT PANEL — raw
    decision variables, no polite endings pretending to be a voice."""
    cases = [
        ("web", {"kind": "page_ingest", "domain": "x.org", "sentences": 12,
                 "top_concepts": ["도커", "이미지"], "revisit": True}),
        ("web", {"topic": "지식", "consensus_backed": 2}),
        ("talk", {"posts": 0, "learned": 0}),
        ("surf", {"kind": "serp_choice", "host": "namu.wiki", "score": 0.94, "seen_before": 1}),
        ("surf", {"topic": "커피", "mode": "search"}),
        ("drive", {"action": "read"}),
        ("monologue", {"accepted": 3}),
    ]
    for kind, e in cases:
        line = af._ticker(kind, e)
        assert line and not line.rstrip(".”\" ").endswith("요"), f"{kind}: {line}"


def test_feed_voice_is_generated_or_silent(monkeypatch):
    """The voice channel returns realize_thought's line or None — silence over molds (owner:
 )."""
    import packages.continuous_self.thought_language as tl
    monkeypatch.setattr(tl, "realize_thought", lambda *a, **k: None)
    e = {"kind": "page_ingest", "domain": "x.org", "topic": "도커", "top_concepts": ["도커", "컨테이너"]}
    assert af._voice("web", e) is None

    monkeypatch.setattr(tl, "realize_thought", lambda *a, **k: "도커라는 개념이 제 안에서 자리를 잡아가요")
    assert af._voice("web", {"kind": "page_ingest", "topic": "도커"}) is None
    v = af._voice("web", {**e, "answer_found": "도커는 컨테이너 런타임이다"})
    assert v and v.startswith("도커라는 개념이") and "도커는 컨테이너 런타임이다" in v