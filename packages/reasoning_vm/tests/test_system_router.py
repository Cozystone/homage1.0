# -*- coding: utf-8 -*-
"""D2 router LOGIC (pure, fast): a question covered by one paragraph → high coverage (would stay S1);
a question whose content is split across paragraphs → low coverage (would escalate to S2). This tests the
routing DECISION signal, not answer accuracy (which is encoder-bound: S2≈S1 measured)."""
from __future__ import annotations

from packages.reasoning_vm.deliberator.system_router import SystemRouter


def _router():
    return object.__new__(SystemRouter)          # no model load — _max_cover is pure


def test_single_paragraph_covers_question_high():
    r = _router()
    paras = [("a", "The Eiffel Tower is a wrought-iron tower located in Paris, France."),
             ("b", "Penguins are flightless birds of the Southern Hemisphere.")]
    cover = r._max_cover("Where is the Eiffel Tower located?", paras)
    assert cover >= 0.6                          # one paragraph covers the question → single-hop (S1)


def test_split_question_low_coverage():
    r = _router()
    # the two entities live in different paragraphs → no single paragraph covers the whole question
    paras = [("film", "Inception is a 2010 science fiction film."),
             ("person", "Christopher Nolan is a British-American director."),
             ("noise", "The Amazon river flows through South America.")]
    cover = r._max_cover("What nationality is the director of Inception?", paras)
    assert cover < 0.6                           # content split → would escalate to S2 (multi-hop)


def test_empty_is_s1():
    r = _router()
    assert r._max_cover("anything", []) == 0.0
