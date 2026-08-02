# -*- coding: utf-8 -*-
"""Code self-understanding — ATANOR answers about its own source, and ONLY about its own source."""
from __future__ import annotations

from packages.graph_scale.code_understanding import answer_code_question, resolve_entity


def test_answers_about_a_real_module():
    r = answer_code_question("speaker_arena.py는 뭐하는 모듈이야?")
    assert r is not None and r["answer_kind"] == "code_self_understanding"
    assert "speaker_arena" in r["answer"]
    # grounded: no external LLM, no fabrication
    g = r["reasoning_certificate"]["guarantees"]
    assert g["external_llm"] is False and g["fabricated_facts"] is False


def test_answers_about_a_real_function():
    r = answer_code_question("realize_thought 함수가 뭐해?")
    assert r is not None
    assert "realize_thought" in r["answer"]


def test_bare_identifier_without_keyword_still_resolves():

    r = answer_code_question("holographic_speaker가 뭐야?")
    assert r is not None and "holographic_speaker" in r["answer"]


def test_fact_questions_are_not_hijacked():
    # a plain word is not code-shaped → must fall through to the fact lanes (None here)
    assert answer_code_question("커피가 뭐야?") is None
    assert answer_code_question("서울은 어느 나라의 수도야?") is None
    assert answer_code_question("너는 누구야?") is None


def test_unknown_identifier_returns_none():
    # code-shaped but not in the graph → honest None, never invents a module
    assert answer_code_question("nonexistent_fake_module_xyz가 뭐야?") is None


def test_resolve_prefers_exact_dotted_name():
    got = resolve_entity("packages.evolution.speaker_arena 설명해줘")
    assert got == "packages.evolution.speaker_arena"
