# -*- coding: utf-8 -*-
"""World-mentor tests — prove the mechanism AND the doctrine boundary without any cost:
the mentor (GPT) is mocked, the web is mocked, and the key assertion is that the mentor's
CURRICULUM text never becomes ATANOR's learned understanding (that comes from the web only)."""
from __future__ import annotations

import json
from collections import namedtuple

import packages.advisor_loop.world_mentor as wm

_Ex = namedtuple("Ex", "reply")

# a curriculum a mentor might give — note it contains NO real definition of city/country/river
_CURRICULUM = ("1. Understand city, country, and river first because they anchor place and movement.\n"
               "2. Strengthen the causes axis to reason about change.\n"
               "3. Organize knowledge as typed entities linked by reusable relation frames.\n"
               "4. Your reflection is too inventory-like; check what breaks if a fact is removed.")

# what ATANOR's OWN web returns per concept — the real understanding, sourced, not from the mentor
_WEB = {
    "city": ("A city is a large human settlement with defined boundaries.",
             "https://example.edu/city", "example.edu"),
    "country": ("A country is a distinct territory with its own government.",
                "https://example.gov/country", "example.gov"),
    "river": ("A river is a natural flowing watercourse toward an ocean or lake.",
              "https://example.org/river", "example.org"),
}


def _seed_graph(path):
    """A tiny graph where 'city'/'country'/'river' appear as OBJECTS but never as SUBJECTS —
    exactly the 'known-of but not understood' foundational-gap shape retrospect_world_gaps hunts."""
    rows = [
        {"subject": "Paris", "bones": [["Paris", "is_a", "city"], ["Paris", "located_in", "France"]]},
        {"subject": "Seoul", "bones": [["Seoul", "is_a", "city"], ["Seoul", "located_in", "Korea"]]},
        {"subject": "France", "bones": [["France", "is_a", "country"]]},
        {"subject": "Korea", "bones": [["Korea", "is_a", "country"]]},
        {"subject": "Nile", "bones": [["Nile", "is_a", "river"]]},
        {"subject": "Amazon", "bones": [["Amazon", "is_a", "river"]]},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _wire(monkeypatch, tmp_path):
    graph = tmp_path / "bones.jsonl"
    _seed_graph(graph)
    monkeypatch.setattr(wm, "GRAPH", graph)
    monkeypatch.setattr(wm, "LEARNED", tmp_path / "learned.jsonl")
    monkeypatch.setattr(wm, "LOG", tmp_path / "mentor.log")
    monkeypatch.setattr(wm, "ask_cli", lambda advisor, prompt, timeout_s=240: _Ex(reply=_CURRICULUM))
    monkeypatch.setattr(wm, "learn_from_web", lambda term, base, used: _WEB.get(term.lower()))
    return graph


def test_retrospect_finds_foundational_gaps(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    gaps = wm.retrospect_world_gaps(scan=100)
    # city/country/river are used as categories but have no subject-entry -> foundational gaps
    fg = set(gaps["foundational_gaps"])
    assert {"city", "country", "river"} & fg, fg
    # a subject that IS explained (paris/france) must NOT be reported as a gap
    assert "paris" not in fg and "france" not in fg
    assert "relation_coverage" in gaps and "is_a" in gaps["relation_coverage"]


def test_mentor_gives_curriculum_not_facts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    gaps = wm.retrospect_world_gaps(scan=100)
    curriculum = wm.ask_mentor_curriculum(gaps, advisor="mock")
    assert curriculum == _CURRICULUM
    # the curriculum is guidance ("understand ... first", "strengthen ... axis"), not a definition
    assert "settlement" not in curriculum.lower()      # the real def of 'city' is NOT in the mentor text


def test_understanding_comes_from_web_not_mentor(monkeypatch, tmp_path):
    """The BINDING boundary: learned understanding is the WEB gloss, never the mentor's words."""
    _wire(monkeypatch, tmp_path)
    out = wm.run_round(learn_first=3, advisor="mock", now_utc=1.0)
    learned = {r["concept"]: r for r in out["learned"]}
    assert set(learned) >= {"city", "country", "river"}
    for concept, rec in learned.items():
        assert rec["understanding"] == _WEB[concept][0]      # exactly the web gloss
        assert rec["understanding"] not in out["curriculum"]  # never sourced from the mentor
        assert rec["source"].startswith("http")               # every fact carries its own citation
    # and the round persisted what ATANOR self-learned
    lines = (tmp_path / "learned.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_no_web_result_yields_no_learned_fact(monkeypatch, tmp_path):
    """If ATANOR's web can't source a concept, it stays UNLEARNED — no fabrication, no mentor fill-in."""
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(wm, "learn_from_web", lambda term, base, used: None)
    out = wm.run_round(learn_first=3, advisor="mock", now_utc=1.0)
    assert out["learned"] == []                              # abstain over fabricate


def test_web_diversity_counter_accumulates_across_round(monkeypatch, tmp_path):
    """The 'wikipedia 작작 써라' fix: one used_domains counter threads through the whole round, so
    later concepts see the domains earlier ones consumed (diversity pressure actually accumulates)."""
    _wire(monkeypatch, tmp_path)
    seen_sizes = []

    def _web(term, base, used):
        seen_sizes.append(sum(used.values()))    # how many prior picks this call can see
        used["en.wikipedia.org"] += 1            # simulate a pick landing on a domain
        return _WEB.get(term.lower())

    monkeypatch.setattr(wm, "learn_from_web", _web)
    wm.run_round(learn_first=3, advisor="mock", now_utc=1.0)
    # first concept sees an empty counter, the next two see the accumulating history — not all zeros
    assert seen_sizes == [0, 1, 2], seen_sizes


def test_gaps_exclude_already_understood_concepts(monkeypatch, tmp_path):
    """Overnight defect: 4 rounds produced 12 journal entries but only 3 unique concepts — the same
    gaps resurfaced forever because self-learned facts never enter the graph (by doctrine). The
    retrospection must subtract the journal so each round reaches genuinely NEW ground."""
    _wire(monkeypatch, tmp_path)
    first = set(wm.retrospect_world_gaps(scan=100)["foundational_gaps"])
    assert {"city", "country"} & first
    (tmp_path / "learned.jsonl").write_text(
        "\n".join(json.dumps({"concept": c, "understanding": "x", "source": "u", "domain": "d"})
                  for c in ("city", "country")), encoding="utf-8")
    again = set(wm.retrospect_world_gaps(scan=100)["foundational_gaps"])
    assert "city" not in again and "country" not in again      # progress, not a treadmill
    assert "river" in again                                    # still-unlearned gaps remain
