# -*- coding: utf-8 -*-
"""Narrative corpus: quality-filtered, deduped, rotating store of surface language — the diet
the self's voice (realize_thought) grows on. Never a fact store.

Fixtures are ENGLISH (doctrine 2026-07-18: the voice's diet is English; the Korean-era fixtures
this file carried were themselves the pollution door test_voice later caught red)."""
from packages.autonomy_kernel import narrative_corpus as nc


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(nc, "CORPUS", tmp_path / "corpus.jsonl")


def test_add_filters_junk_and_dedupes(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    lines = [
        "A virtual machine is a software environment that behaves like a real computer.",  # good
        "A virtual machine is a software environment that behaves like a real computer.",  # dup
        "http://spam.example.com click this link",                                         # url
        "Short.",                                                                          # too short
        "%%%### {{{}}} ===",                                                               # debris
        "A knowledge graph keeps relations between concepts as nodes and edges.",          # good
    ]
    assert nc.add_lines(lines, source="test") == 2
    assert nc.add_lines(lines, source="test") == 0          # idempotent across calls (hash store)
    tail = nc.corpus_tail(10)
    assert len(tail) == 2 and all("http" not in t for t in tail)


def test_korean_is_refused_at_intake(tmp_path, monkeypatch):
    """The English-only door, mechanically: the exact Naver-debris shape that used to pass (ends in
    a legitimate Korean sentence-ender) and clean Korean prose are BOTH refused — the boundary is
    the language, not the quality."""
    _use_tmp_store(tmp_path, monkeypatch)
    assert nc.add_lines(["가상머신은 실제 컴퓨터처럼 동작하는 소프트웨어 환경이에요."],
                        source="test") == 0
    assert nc.add_lines(["정신건강의학과 UP 0 0 2분 전 이런 옷 뭔가요"], source="test") == 0


def test_tail_filters_by_source_and_stats_count(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    nc.add_lines(["I talked architecture with the other agents on the commons today."],
                 source="moltbook")
    nc.add_lines(["A sentence read on expedition is absorbed as surface language only."],
                 source="expedition")
    assert len(nc.corpus_tail(10, sources=("moltbook",))) == 1
    s = nc.stats()
    assert s["total"] == 2 and s["by_source"]["moltbook"] == 1


def test_mine_text_splits_sentences(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    text = ("A virtual machine is an execution environment that imitates a physical computer. "
            "You can run an entire operating system on top of it. OK. "
            "Such isolated environments are widely used for server deployment.")
    mined = nc.mine_text(text)
    assert len(mined) == 3                              # 'OK.' is below the length floor
    assert all(m.endswith(".") for m in mined)


def test_mine_triples_produces_english_narrative(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    out = nc.mine_triples([("virtual machine", "used_for", "server deployment"), ("", "x", "y")])
    assert len(out) == 1
    assert "virtual machine" in out[0].lower() and "server deployment" in out[0].lower()
    assert not any("가" <= ch <= "힣" for ch in out[0])   # the Korean fallback is dead


def test_rotation_caps_the_store(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(nc, "_MAX_LINES", 5)
    for i in range(8):
        nc.add_lines([f"Distinct sentence number {i} is written out long enough to pass the gate."],
                     source="test")
    assert nc.stats()["total"] <= 5


def test_register_classifies_by_surface_morphology():
    assert nc.register("Water is a compound made of hydrogen and oxygen.") == "encyclopedic"
    assert nc.register("I feel a little excited about today.") == "conversational"
    assert nc.register("Which side does your heart lean toward?") == "question"
    assert nc.register("The final round happened in Naypyidaw that September.") == "narrative"


def test_balanced_tail_lifts_voice_share_under_encyclopedic_flood(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    # realistic flood ordering: the scarce human-voice lines are OLD (added first), then the
    # accelerated wiki lane buries them under recent encyclopedic declaratives — so the plain
    # tail is nearly all encyclopedic and balanced sampling must reach back for the buried lines
    old = [f"I keep wondering about thought number {i} today." for i in range(10)]   # conversational
    old += [f"What does concept number {i} really mean?" for i in range(6)]          # question
    nc.add_lines(old, source="test")
    nc.add_lines([f"Concept number {i} is an object of some field of study." for i in range(120)],
                 source="test")                                                      # flood (recent)

    def voice_share(rows):
        voice = sum(1 for t in rows if nc.register(t) in nc._VOICE_REGISTERS)
        return voice / max(1, len(rows))

    plain = nc.corpus_tail(30, balanced=False)
    balanced = nc.corpus_tail(30, balanced=True)
    # the raw tail is nearly all encyclopedic; balanced sampling must pull the scarce
    # human-voice registers forward so the voice isn't fit on a monotone diet
    assert voice_share(balanced) > voice_share(plain)
    assert voice_share(balanced) >= 0.30
    assert len(balanced) == 30

    st = nc.stats()
    assert "by_register" in st and st["by_register"]["encyclopedic"] == 120
    assert 0.0 <= st["voice_share"] <= 1.0
