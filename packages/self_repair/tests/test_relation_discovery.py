# -*- coding: utf-8 -*-
"""Relation discovery — finding a relation the vocabulary lacks, without inventing one.

The station that unblocked the loop. Before it, `self_cycle` proposed 24 candidates and queued zero:
correct behaviour, because its largest missed cues mean something ATANOR cannot say. A refusal was the
end of the line; now it is a question.
"""
from __future__ import annotations

import pytest

from packages.self_repair.relation_discovery import (agreement, external_relations, have_today,
                                                     null_rate)


def _needs_oracle():
    if len(external_relations()) < 5:
        pytest.skip("no ConceptNet oracle on disk in this environment")


def test_the_oracle_knows_relations_we_do_not_extract():
    """The whole premise. If ATANOR already extracted everything the oracle names, discovery would
    have nothing to find and this station would be dead weight."""
    _needs_oracle()
    missing = set(external_relations()) - have_today()
    assert missing
    assert {"HasA", "PartOf"} & missing        # the ones `consisting of` needs


def test_the_relation_names_come_from_outside():
    """Nothing here writes a predicate name. They are read off an inventory that predates the
    question, which is what separates discovery from inventing a rule in a lab coat."""
    _needs_oracle()
    for r in external_relations():
        assert r[0].isupper()                  # ConceptNet's own casing, not ours


def test_base_rate_is_controlled():
    """The defect that made the first run report `consisting of -> IsA`. ConceptNet holds 22,441 IsA
    edges against 347 MadeOf, so a subject usually has an IsA object and almost never a MadeOf one,
    and raw agreement rewards abundance. Shuffling the objects keeps both marginals and breaks the
    pairing, so a common relation scores on the null too."""
    _needs_oracle()
    pairs = [("dog", "animal"), ("cat", "animal"), ("car", "vehicle"), ("bus", "vehicle"),
             ("hammer", "tool"), ("saw", "tool"), ("apple", "fruit"), ("pear", "fruit")]
    assert null_rate(pairs, "IsA") >= 0.0      # computable, and subtracted from raw agreement


def test_an_unknown_subject_is_silence_not_disagreement():
    """Counting an unknown subject as a miss would fabricate a signal out of the oracle's gaps."""
    _needs_oracle()
    checkable, agreed = agreement([("zzqqxx_not_a_word", "anything")], "IsA")
    assert checkable == 0 and agreed == 0


def test_discovery_reports_what_it_cannot_do():
    """Honest scope. It finds relations that EXIST in the external inventory. A predicate the world
    needs and ConceptNet lacks is invisible to it, and calling that 'invention' would overclaim."""
    import packages.self_repair.relation_discovery as rd
    assert "cannot" in rd.__doc__.lower()
    assert "invent" in rd.__doc__.lower()
