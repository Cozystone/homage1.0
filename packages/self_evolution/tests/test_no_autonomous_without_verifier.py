# -*- coding: utf-8 -*-
"""SAFETY INVARIANT: a domain lacking a verifier is NEVER marked autonomous.

This is the load-bearing safety property of the whole orchestrator. No measured gain, no headroom, and
no hand override may promote a verifier-less domain to autonomous execution — it can only ever surface
as a flagged operator proposal that names the missing verifier.
"""
from __future__ import annotations

from packages.self_evolution import build_weakness_map, load_registry, plan_next_evolution
from packages.self_evolution.evolution_registry import evolvability_probes


def test_registry_probe_never_marks_a_verifierless_loop_autonomous():
    for loop in load_registry():
        flags = evolvability_probes(loop)
        if not flags["verifier_exists"]:
            assert flags["autonomous_safe"] is False, loop.domain
            assert flags["evolvable"] is False, loop.domain


def test_autonomous_implies_verifier_for_every_sensed_domain():
    """The implication autonomous_safe -> verifier_exists must hold for EVERY domain on the real map."""
    for w in build_weakness_map():
        if w.autonomous_safe:
            assert w.verifier_exists is True, w.domain
            # ...and an autonomous domain is never architecture-gated
            assert w.generator_kind != "architecture", w.domain


def test_fluency_has_no_verifier_and_is_only_a_proposal():
    """Fluency (register naturalness) has no crisp verifier -> operator proposal, never an invocation."""
    plan = plan_next_evolution(write=False)
    entry = next(e for e in plan["plan"] if e["domain"] == "fluency")
    assert entry["verifier_exists"] is False
    assert entry["kind"] == "operator_proposal"
    assert entry["autonomous_safe"] is False
    assert "verifier" in entry["missing_piece"].lower()


def test_consciousness_is_architecture_gated_not_autonomous():
    """Consciousness has all three pieces, but its generator is architecture-level -> not autonomous."""
    plan = plan_next_evolution(write=False)
    entry = next(e for e in plan["plan"] if e["domain"] == "consciousness")
    assert entry["autonomous_safe"] is False
    assert entry["kind"] == "operator_proposal"


def test_no_invocation_entry_is_ever_non_autonomous():
    """Every emitted invocation spec must be autonomous-safe AND verifier-backed."""
    plan = plan_next_evolution(write=False)
    for e in plan["plan"]:
        if e["kind"] == "invocation":
            assert e["autonomous_safe"] is True, e["domain"]
            assert e["verifier_exists"] is True, e["domain"]
