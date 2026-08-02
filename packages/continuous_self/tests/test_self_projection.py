# -*- coding: utf-8 -*-
"""SL-1: the self must be sayable in the world's own vocabulary, or not said at all."""
from __future__ import annotations

from packages.continuous_self.self_projection import (
    SELF_SUBJECT, project_parts, project_state, projection_coverage)


class _State:
    mode = "observing"
    focus = "reading its own graph"
    inquiry_driver = "uncertainty"
    unrelated = "should not be projected"


def test_state_projects_only_through_graph_predicates():
    allowed = frozenset({"has_property", "has_a"})
    triples = project_state(_State(), allowed=allowed)
    assert triples, "a live state with real fields must project something"
    for subject, predicate, obj in triples:
        assert subject == SELF_SUBJECT
        assert predicate in allowed          # never a self-only predicate invented for the occasion
        assert obj.strip()


def test_a_predicate_the_graph_does_not_use_is_dropped_not_invented():
    """The whole discipline: if the world has no word for it, the self stays silent about it."""
    assert project_state(_State(), allowed=frozenset()) == []
    assert project_parts(["deliberator"], allowed=frozenset()) == []


def test_parts_come_from_the_caller_so_a_missing_organ_is_visible():
    """A hardcoded organ list could never notice an organ that is absent. The census is an argument."""
    allowed = frozenset({"has_a"})
    assert project_parts([], allowed=allowed) == []
    two = project_parts(["deliberator", "conformal_gate"], allowed=allowed)
    assert [t[2] for t in two] == ["deliberator", "conformal_gate"]


def test_empty_and_placeholder_values_never_become_facts():
    class Blank:
        mode = ""
        focus = "   "
        inquiry_driver = "none"
    assert project_state(Blank(), allowed=frozenset({"has_property"})) == []


def test_coverage_reports_what_the_self_cannot_yet_say():
    """`dropped_for_missing_predicate` empty == the self is fully expressible in world vocabulary."""
    cov = projection_coverage(_State(), ["deliberator"])
    assert set(cov) >= {"graph_predicates", "self_predicates_used",
                        "dropped_for_missing_predicate", "state_triples", "part_triples"}
    assert isinstance(cov["dropped_for_missing_predicate"], list)
