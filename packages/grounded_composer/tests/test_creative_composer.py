# -*- coding: utf-8 -*-
"""Creative composer — the next-token fusion: grounded, labeled, never forced."""

from __future__ import annotations

import packages.grounded_composer.creative_composer as cc


def _fake_corpus(theme):
    return ([
        f"{theme}는 지구의 표면에 넓게 물이 고여 있는 곳이다.",
        "물은 색과 맛과 냄새가 없는 액체이다.",
        "지구는 태양계의 셋째 행성이다.",
        "표면은 사물의 가장 바깥쪽 부분이다.",
        "물은 생명의 근원이 되는 액체이다.",
    ], ["http://src/1"], [theme, "물", "지구"])


def test_poem_composes_from_grounded_corpus(monkeypatch):
    monkeypatch.setattr(cc, "_themed_corpus", lambda t: _fake_corpus(t))
    p = cc.compose_poem("바다")
    assert p is not None
    assert len(p["lines"]) >= 2
    assert p["guarantees"]["creative_mode"] is True
    assert p["guarantees"]["factual_claims"] is False
    assert p["guarantees"]["external_llm"] is False
    # every hangul unit in the holographic lines occurred in the corpus
    corpus_tokens = set()
    for s in _fake_corpus("바다")[0]:
        corpus_tokens.update(cc._CONTENT.findall(s))
    import re as _re
    for line in p["lines"]:
        if "인상" in line or "결을 닮았다" in line:
            continue  # impression/metaphor lines have their own grounding
        for tok in _re.findall(r"[가-힣]{2,}", line):
            assert tok in corpus_tokens, f"non-corpus unit leaked: {tok}"


def test_no_corpus_means_silence(monkeypatch):
    monkeypatch.setattr(cc, "_themed_corpus", lambda t: ([], [], []))
    assert cc.compose_poem("유니콘") is None  # silence over pastiche


def test_tiny_corpus_means_silence(monkeypatch):
    monkeypatch.setattr(cc, "_themed_corpus",
                        lambda t: (["짧은 문장 하나이다."], [], [t]))
    assert cc.compose_poem("무엇") is None


def test_near_duplicate_lines_collapse():
    assert cc._too_similar("사랑은 사람을 몹시 좋아함", "사람을 몹시 좋아함")
    assert not cc._too_similar("바다는 넓다", "음악은 소리의 예술이다")


def test_content_words_strip_josa():
    words = cc._content_words("바다는 지구의 표면에 넓게 물이 고여 있다")
    assert "바다" in words and "지구" in words and "표면" in words
