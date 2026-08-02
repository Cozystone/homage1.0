# -*- coding: utf-8 -*-
"""The faithfulness checker must do BOTH jobs, and the pair is what makes it worth anything.

A checker that passes everything is decoration; a checker that fails everything is noise. So every
test here comes with its opposite: truthful prose passes, invented prose fails, and the live answer
path is held to the same bar as the synthetic cases.
"""
from __future__ import annotations

from packages.graph_scale.roundtrip_faithfulness import Proposition as P
from packages.graph_scale.roundtrip_faithfulness import check, propositions_from_answer

PROPS = [P("Rooms", "defined_at", "packages/workspace/rooms.py:90"),
         P("Rooms", "has_method", "place"),
         P("Rooms", "has_method", "census")]


def test_truthful_prose_is_faithful():
    v = check(PROPS, "`Rooms` is a class, at packages/workspace/rooms.py:90. "
                     "It defines `place` and `census`.")
    assert v.faithful and not v.added


def test_invented_claim_is_caught():
    """The floor. A method that exists in no supplied proposition is a fabrication, and naming it is
    the whole job."""
    v = check(PROPS, "`Rooms` defines `place`, `census` and `delete_everything`.")
    assert not v.faithful
    assert "delete_everything" in v.added


def test_a_plausible_wrong_citation_is_caught():
    """The subtle case, and the one a human reviewer misses: the line number is off by one. A
    citation that looks right and points somewhere else is worse than no citation, because it
    survives a skim."""
    v = check(PROPS, "`Rooms` is a class, at packages/workspace/rooms.py:91.")
    assert not v.faithful
    assert any("rooms.py:91" in a for a in v.added)


def test_brevity_is_not_infidelity():
    """A good answer is usually shorter than everything it could have said. Counting omission as
    failure would push the realizer toward reciting the graph, which is the failure this whole line
    of work exists to move away from."""
    v = check(PROPS, "`Rooms` is a class.")
    assert v.faithful and v.coverage < 1.0
    assert v.dropped                                  # reported, but not a failure


def test_require_all_makes_omission_fail_when_asked():
    v = check(PROPS, "`Rooms` is a class.", require_all=True)
    assert not v.faithful


def test_live_code_answers_are_faithful_and_still_checkable():
    """The real path, both directions in one test: what the lane actually says is faithful, and the
    same certificate still catches an invention appended to it.

    This pins the repair that made the check meaningful. The certificate used to record only cited
    locations and a sample of evidence concepts, so honest sentences -- which truthfully mention the
    module a class sits in and the functions it calls -- were scored as fabrications. The fix
    belonged in the certificate, not in loosening the checker, and this test fails if that record
    ever goes back to being partial."""
    from packages.graph_scale.code_understanding import answer_code_question
    answer = answer_code_question("what is the Rooms class")
    if answer is None:                                # no ingested graph in this environment
        return
    props = propositions_from_answer(answer)
    assert props, "the certificate must record the propositions the answer was built from"
    assert check(props, answer["answer"]).faithful
    assert not check(props, answer["answer"] + " It also calls `launch_missiles`.").faithful
