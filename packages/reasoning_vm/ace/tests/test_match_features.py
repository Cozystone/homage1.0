# -*- coding: utf-8 -*-
"""B1 L1 — DrQA-style match features must fire where the passage echoes the question and stay quiet
elsewhere; the idf weighting must favour rare matches over stopwords."""
from __future__ import annotations

from packages.reasoning_vm.ace.match_features import (NFEAT, FEATURE_NAMES, passage_match_features,
                                                      overlap_score, build_idf, _stem)


def _col(feats, name):
    j = FEATURE_NAMES.index(name)
    return [row[j] for row in feats]


def test_exact_and_stem_match_fire_on_echoed_tokens():
    q = "Where does the frog live?"
    p = "The frog lives in a pond."
    feats = passage_match_features(q, p)
    assert len(feats) == len(p.split()) - 0    # one row per passage token (punctuation stripped)
    exact = _col(feats, "exact")
    stem = _col(feats, "stem")
    toks = p.replace(".", "").split()
    assert exact[toks.index("frog")] == 1.0            # "frog" is verbatim in the question
    assert stem[toks.index("lives")] == 1.0            # "lives" stems to "live" ~ question's "live"


def test_absent_tokens_do_not_match():
    feats = passage_match_features("what colour is the sky", "a dog barks loudly")
    assert sum(_col(feats, "lower")) == 0.0            # no overlap at all


def test_feature_width_is_stable():
    feats = passage_match_features("q here", "a b c d")
    assert all(len(row) == NFEAT for row in feats)


def test_idf_downweights_stopwords_relative_to_rare_terms():
    idf = build_idf(["the cat sat", "the dog ran", "the fish swam", "a mitochondrion is an organelle"])
    # "the" appears in 3/4 docs (low idf); "mitochondrion" in 1/4 (high idf)
    assert idf["mitochondrion"] > idf["the"]


def test_overlap_score_rewards_question_echo():
    idf = build_idf(["the frog lives in a pond", "a car has wheels", "the sun is hot"])
    q = "where does the frog live"
    hi = overlap_score(q, "the frog lives in a pond", idf)
    lo = overlap_score(q, "a car has four wheels", idf)
    assert hi > lo                                     # the echoing passage scores higher


def test_stem_is_conservative():
    assert _stem("cities") == "city"
    assert _stem("running") == "runn" or _stem("running") == "run"   # bridges running~run family
    assert _stem("is") == "is"                          # too short to strip -> unchanged
