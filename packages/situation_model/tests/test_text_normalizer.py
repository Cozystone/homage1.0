# -*- coding: utf-8 -*-
"""Text normalizer — every guard here was PAID FOR by a measured regression during the noise-wall
work (2026-07-21), so each test names the failure that taught it. The layer's contract: repair
SURFACE, never meaning; when unsure, change nothing; clean text passes through untouched."""
from __future__ import annotations

from packages.situation_model.text_normalizer import (build_canon_map, apply_canon, canonicalize,
                                                      repair_function_words, repair_with_lexicon,
                                                      segment_by_verbs, snap_to_frame_vocab)


# ---------- within-passage majority vote ----------

def test_minority_typo_folds_onto_majority_spelling():
    text = ("Mary went to the kitchen. John went to the kitchen. Sandra went to the kitchen. "
            "Daniel went to the kitchin.")
    assert canonicalize(text).count("kitchen") == 4


def test_closed_class_words_are_never_folded():
    """PAID FOR: 'then' (rare) was folded into 'they' (frequent) in compound-coreference text,
    turning 'Then Daniel went...' into 'They Daniel went...' — qa13 dropped 1.000 -> 0.918.
    Frequency evidence does not apply to the closed class."""
    text = ("They went to the office. They took the football. They dropped the football. "
            "They found the football. Then Daniel went to the hallway.")
    canon = build_canon_map(text)
    assert "then" not in canon and "than" not in canon
    assert "Then Daniel" in apply_canon(text, canon)


def test_two_genuinely_common_words_never_merge():
    text = ("The cat sat on the mat. The cat saw the rat. The rat ran from the cat. "
            "The bat flew over the rat. The bat liked the mat.")
    canon = build_canon_map(text)
    assert not canon        # cat/rat/bat/mat are all frequent — none is a variant of another


# ---------- verb-count segmentation (case+punct both gone) ----------

def test_segments_lowercased_unpunctuated_text_by_verbs():
    """PAID FOR: case_punct@0.25 strips periods AND case; the capitalization fallback dies and the
    whole passage parsed as one blob — acc 0.037. One finite verb per clause survives both."""
    blob = "mary went to the kitchen john moved to the garden sandra journeyed to the office"
    segs = segment_by_verbs(blob)
    assert len(segs) == 3
    assert segs[0].startswith("mary") and segs[1].startswith("john") and segs[2].startswith("sandra")


def test_segmentation_keeps_determiner_with_its_subject():
    blob = "the girl took the apple the boy went to the school"
    segs = segment_by_verbs(blob)
    assert len(segs) == 2 and segs[1].startswith("the boy")


def test_single_clause_is_not_split():
    assert segment_by_verbs("mary went to the beautiful garden") == \
        ["mary went to the beautiful garden"]


# ---------- frame-vocab snapping (typos in predicates) ----------

def test_corrupted_preposition_snaps_with_priority_tiebreak():
    """PAID FOR: 'tp' is one edit from both 'to' and 'up'; refusing every collision left 'went tp
    the bathroom' storing 'tp the bathroom' as a location. Load-bearing keywords win ties."""
    assert snap_to_frame_vocab("Sandra went tp the bathroom") == "Sandra went to the bathroom"


def test_corrupted_verb_snaps_to_frame_verb():
    assert snap_to_frame_vocab("mary wnet to the kitchen") == "mary went to the kitchen"


def test_content_words_are_not_snapped():
    s = "the milk and the apple stayed there"
    assert snap_to_frame_vocab(s) == s


# ---------- function-word repair (fragmentation) ----------

def test_motion_without_to_is_repaired():
    assert repair_function_words("mary went kitchen").startswith("mary went to ")


def test_wh_question_without_copula_is_repaired():
    """PAID FOR: fragment noise turned 'Where is Mary?' into 'Where Mary?' — the WORLD was built
    correctly and we abstained anyway, because the question itself had become unreadable."""
    assert repair_function_words("Where Mary?").lower().startswith("where is mary")
    # an intact question is left exactly alone
    assert repair_function_words("Where is Mary?") == "Where is Mary?"


# ---------- own-lexicon repair (every mention corrupted) ----------

def test_unknown_word_repairs_to_known_vocabulary():
    """The 'natural' family's core case: EVERY mention of a room is misspelled, so no majority
    exists inside the passage — but ATANOR knows the word itself."""
    out = repair_with_lexicon("sandra travelled to the bathrom")
    assert "bathroom" in out


def test_proper_names_are_never_lexicon_corrected():
    """PAID FOR: names are exactly what a general vocabulary lacks; 'correcting' them cost bAbI
    0.976 -> 0.9676 on the first wiring. A capitalized token is a name and is left alone."""
    s = "Sandra gave the milk to Daniel"
    assert repair_with_lexicon(s) == s


def test_known_words_are_never_touched():
    s = "the kitchen is separate from the garden"
    assert repair_with_lexicon(s) == s


# ---------- the honest floor ----------

def test_clean_text_round_trips_through_every_layer():
    s = "Mary went to the kitchen. Then she picked up the apple."
    assert apply_canon(s, build_canon_map(s)) == s
    assert snap_to_frame_vocab(s) == s
    assert repair_with_lexicon(s) == s
