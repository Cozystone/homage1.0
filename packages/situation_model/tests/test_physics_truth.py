# -*- coding: utf-8 -*-
"""Physics-truth gate — keep ATANOR clean when it learns from a world (owner: make Realcity's physics
real "so that ATANOR is not contaminated"). These tests pin the safety guarantee: true physics is
learnable, physically-impossible 'physics' is quarantined and never learned, and when the stated
conditions are insufficient the gate ABSTAINS rather than guessing — the same honesty floor as
mechanism.py. The headline property (test_gate_never_accepts_a_violation) is the contamination shield."""
from __future__ import annotations

from packages.situation_model.physics_truth import (
    ACCEPTED,
    QUARANTINED,
    UNDECIDED,
    PhysicsObservation,
    from_trajectory,
    screen,
    verify,
)


# ---- true physics is learnable ----------------------------------------------------

def test_unsupported_disturbed_thing_falls_is_accepted():
    v = verify(PhysicsObservation("fall", "cup", {"at_edge": True, "disturbed": True}))
    assert v.status == ACCEPTED and v.law == "unsupported-things-fall"


def test_open_path_traverse_is_accepted():
    v = verify(PhysicsObservation("traverse", "bus", {"blocked": False, "solid": False}))
    assert v.status == ACCEPTED


def test_bounded_rebound_is_accepted():
    v = verify(PhysicsObservation("bounce", "ball", {}, {"drop": 5.0, "apex": 3.8}))
    assert v.status == ACCEPTED and v.law == "restitution-bounded"


def test_clean_contact_rest_is_accepted():
    v = verify(PhysicsObservation("rest", "box", {"supported": True}, {"penetration": 0.004}))
    assert v.status == ACCEPTED


# ---- physically-impossible 'physics' is quarantined (never learned) ---------------

def test_supported_undisturbed_fall_is_quarantined():
    """The arcade bug where a thing on a table just drops through it."""
    v = verify(PhysicsObservation("fall", "plate", {"supported": True, "disturbed": False}))
    assert v.status == QUARANTINED and v.law == "support-holds"


def test_unsupported_hover_is_quarantined():
    v = verify(PhysicsObservation("float", "crate", {"supported": False, "applied_force": False}))
    assert v.status == QUARANTINED and v.law == "gravity-pulls-down"


def test_traverse_through_blocked_path_is_quarantined():
    """The 'taxi drives through the wall' contamination the owner worried about."""
    v = verify(PhysicsObservation("traverse", "taxi", {"blocked": True}))
    assert v.status == QUARANTINED and v.law == "blocked-path-is-impassable"


def test_rebound_higher_than_drop_is_quarantined():
    v = verify(PhysicsObservation("bounce", "ball", {}, {"drop": 2.0, "apex": 3.5}))
    assert v.status == QUARANTINED and v.law == "energy-not-created"


def test_deep_interpenetration_is_quarantined():
    v = verify(PhysicsObservation("rest", "box", {"supported": True}, {"penetration": 0.5}))
    assert v.status == QUARANTINED and v.law == "no-deep-interpenetration"


# ---- honesty floor: abstain when conditions are insufficient ----------------------

def test_fall_with_unknown_support_is_undecided():
    v = verify(PhysicsObservation("fall", "thing", {}))          # no support/edge/disturbance stated
    assert v.status == UNDECIDED


def test_traverse_unknown_solidity_is_undecided():
    v = verify(PhysicsObservation("traverse", "cart", {}))
    assert v.status == UNDECIDED


def test_unknown_event_kind_is_undecided():
    v = verify(PhysicsObservation("teleport", "wizard", {}))
    assert v.status == UNDECIDED


# ---- trajectory classification (real engine output -> event) ----------------------

def test_settling_trajectory_classifies_as_clean_rest():
    """A box dropped from 5 that settles at 0.25 on a support at y=0 (real Rapier behaviour)."""
    ys = [5.0, 3.0, 1.0, 0.30, 0.252, 0.250, 0.249]
    obs = from_trajectory("box", ys, support_y=0.25, conditions={})
    assert obs.kind == "rest"
    assert verify(obs).status == ACCEPTED                        # penetration ~0 -> learnable


def test_tunnelling_trajectory_is_caught_as_penetration():
    """A fake engine where the box sinks far past its support -> quarantined, not learned."""
    ys = [5.0, 1.0, -10.0, -25.0, -39.2]
    obs = from_trajectory("box", ys, support_y=0.25, conditions={})
    assert obs.kind == "rest"
    assert verify(obs).status == QUARANTINED                     # deep penetration


def test_spontaneous_rise_trajectory_is_quarantined():
    ys = [1.0, 1.4, 2.0, 2.9]                                    # rose with no force
    obs = from_trajectory("crate", ys, conditions={"applied_force": False, "supported": False})
    assert obs.kind == "rise"
    assert verify(obs).status == QUARANTINED


# ---- the contamination shield: the gate NEVER accepts a violation -----------------

def test_gate_never_accepts_a_violation():
    violations = [
        PhysicsObservation("fall", "plate", {"supported": True, "disturbed": False}),
        PhysicsObservation("float", "crate", {"supported": False, "applied_force": False}),
        PhysicsObservation("traverse", "taxi", {"blocked": True}),
        PhysicsObservation("bounce", "ball", {}, {"drop": 1.0, "apex": 9.9}),
        PhysicsObservation("rest", "box", {"supported": True}, {"penetration": 1.0}),
    ]
    truths = [
        PhysicsObservation("fall", "cup", {"at_edge": True, "disturbed": True}),
        PhysicsObservation("traverse", "bus", {"blocked": False}),
        PhysicsObservation("bounce", "ball", {}, {"drop": 5.0, "apex": 3.8}),
    ]
    out = screen(violations + truths)
    # every violation quarantined, none leaked into the learnable set
    assert len(out[QUARANTINED]) == len(violations)
    assert len(out[ACCEPTED]) == len(truths)
    learnable_subjects = {v.observation.subject for v in out[ACCEPTED]}
    assert learnable_subjects == {"cup", "bus", "ball"}          # no taxi/plate/crate ever learned
