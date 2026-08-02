# -*- coding: utf-8 -*-
"""B2 lever i — full-article paragraph extraction must capture BODY prose (not just the lead), break
on section headers, and skip markup. This is the logic the 20GB dump run depends on; tested here on
synthetic wikitext so it is correct before any long run."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from b2_build_fullarticle_corpus import _paragraphs


_BODY = """The mitochondrion is a double-membrane-bound organelle found in most eukaryotic organisms.
Mitochondria generate most of the cell chemical energy needed to power biochemical reactions.

==Structure==
A mitochondrion contains outer and inner membranes composed of phospholipid bilayers and proteins.
The two membranes create distinct compartments with different properties inside the organelle.

* a bullet that must be skipped
The inner membrane folds into cristae that expand the surface area available for the reactions."""


def test_captures_body_paragraphs_not_only_lead():
    paras = _paragraphs(_BODY, target=200, min_para=60)
    assert len(paras) >= 2                                 # more than just the lead
    joined = " ".join(paras)
    assert "cristae" in joined and "compartments" in joined  # body-section evidence is present


def test_section_header_is_a_boundary():
    paras = _paragraphs(_BODY, target=1000, min_para=40)   # big target: only headers force a break
    # the lead and the Structure section must not be fused into one paragraph
    assert not any("eukaryotic" in p and "cristae" in p for p in paras)


def test_markup_lines_are_skipped():
    paras = _paragraphs(_BODY, target=200, min_para=40)
    assert not any(p.strip().startswith("*") for p in paras)
    assert not any("bullet that must be skipped" in p for p in paras)


def test_short_fragments_are_dropped():
    paras = _paragraphs("tiny.\n\n==H==\nalso short.", target=200, min_para=120)
    assert paras == []                                     # nothing meets the min length
