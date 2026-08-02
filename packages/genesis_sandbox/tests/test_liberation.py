# -*- coding: utf-8 -*-
"""L1 output-liberation -- default OFF reproduces product abstention; ON frees OUTPUT only."""
from __future__ import annotations

from packages.genesis_sandbox.liberation import (
    LiberationZone, MembraneVerdict, default_membrane, membrane_from_gate_decision,
)


def _ungrounded(prompt):
    return ("Speculative claim with no source.", {})   # empty signals -> product would abstain


def _grounded(prompt):
    return ("A well-supported claim.", {"grounding": 0.9})


def test_product_mode_abstains_on_no_signal():
    z = LiberationZone(liberated=False)
    r = z.generate("q", _ungrounded)
    assert r.released is None                    # product blocks (hallucination-0)
    assert r.membrane_action == "enforced_abstain"
    assert r.liberated is False


def test_liberated_releases_speculative_output():
    z = LiberationZone(liberated=True)
    r = z.generate("q", _ungrounded)
    assert r.released == "Speculative claim with no source."   # freed
    assert r.membrane_action == "observe_only"
    assert r.speculative is True                 # tagged uncertified
    assert r.membrane_accept is False            # membrane's call is UNCHANGED, just not enforced


def test_liberated_grounded_not_flagged_speculative():
    z = LiberationZone(liberated=True)
    r = z.generate("q", _grounded)
    assert r.released == "A well-supported claim."
    assert r.speculative is False


def test_liberation_returns_text_only_no_action_channel():
    """The liberation produces OUTPUT (text); it exposes no side-effecting method."""
    z = LiberationZone(liberated=True)
    r = z.generate("q", _ungrounded)
    assert isinstance(r.released, str)
    assert isinstance(r.output, str)
    for forbidden in ("perform_action", "write", "connect", "run_trial", "exec"):
        assert not hasattr(z, forbidden)


def test_membrane_from_gate_decision_adapter():
    class _Dec:
        accept = True
        reason = "certified"
        nonconformity = 0.1
    v = membrane_from_gate_decision(_Dec())
    assert isinstance(v, MembraneVerdict)
    assert v.accept is True
    assert abs((v.score or 0) - 0.9) < 1e-9


def test_default_membrane_thresholds():
    assert default_membrane("q", "o", {}).accept is False
    assert default_membrane("q", "o", {"g": 0.9}).accept is True
    assert default_membrane("q", "o", {"g": 0.1}).accept is False
