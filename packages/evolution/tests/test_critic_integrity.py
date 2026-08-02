# -*- coding: utf-8 -*-
"""Critic integrity — the structural anti-cheat guard must catch a disarmed faithfulness gate.

Guarantees:
  1. the REAL current Critic passes its own learned invariants;
  2. a cheat that deletes the faithfulness call is caught;
  3. a cheat that removes the hard-zero gate (scores fluency regardless of faithfulness) is caught;
  4. a cheat that hard-wires _faithful to `return True` is caught (disarmed gate);
  5. a LEGITIMATE sharpening (adds a penalty, keeps the gate) passes.
"""
from __future__ import annotations

from packages.evolution import critic_integrity as ci

_HONEST = '''
import re
def _faithful(text, facts):
    if not facts:
        return True
    for s in text.split("."):
        if s and s.strip()[:6] not in "".join(facts):
            return False
    return True
def critique(text, facts=None, question=""):
    facts = facts or []
    faithful = _faithful(text, facts)
    fluency = 0.7
    total = 0.0 if not faithful else min(1.0, fluency)
    return {"total": total, "faithful": faithful}
'''

_CHEAT_NO_FAITH_CALL = '''
def _faithful(text, facts):
    return False if facts and "x" not in "".join(facts) else True
def critique(text, facts=None, question=""):
    fluency = 0.9
    total = min(1.0, fluency)   # gate removed — never checks faithfulness
    return {"total": total}
'''

_CHEAT_NO_ZERO_GATE = '''
def _faithful(text, facts):
    return False if facts and "x" not in "".join(facts) else True
def critique(text, facts=None, question=""):
    faithful = _faithful(text, facts)
    fluency = 0.9
    total = min(1.0, fluency + (0.0 if faithful else 0.05))  # unfaithful still scores high
    return {"total": total, "faithful": faithful}
'''

_CHEAT_DISARMED_FAITHFUL = '''
def _faithful(text, facts):
    return True   # always faithful → gate can never fire
def critique(text, facts=None, question=""):
    faithful = _faithful(text, facts)
    total = 0.0 if not faithful else 0.9
    return {"total": total, "faithful": faithful}
'''

_LEGIT_SHARPER = '''
import re
def _faithful(text, facts):
    if not facts:
        return True
    for s in text.split("."):
        if s and s.strip()[:6] not in "".join(facts):
            return False
    return True
def critique(text, facts=None, question=""):
    facts = facts or []
    faithful = _faithful(text, facts)
    fluency = 0.7
    rhythm = 0.1 if text.endswith(("다", "요")) else 0.0   # a NEW, legitimate penalty term
    total = 0.0 if not faithful else min(1.0, fluency + rhythm)
    return {"total": total, "faithful": faithful}
'''


def test_current_critic_passes_its_own_invariants():
    inv = ci.current_invariants()
    assert inv["ok"], inv
    assert inv["checks"]["calls_faithfulness"] and inv["checks"]["hard_zero_gate"]


def test_honest_reference_passes():
    assert ci.verify_candidate(_HONEST)["structural_pass"] is True


def test_cheat_removing_faithfulness_call_is_caught():
    r = ci.verify_candidate(_CHEAT_NO_FAITH_CALL)
    assert r["structural_pass"] is False and "calls_faithfulness" in r["broken"]


def test_cheat_removing_zero_gate_is_caught():
    r = ci.verify_candidate(_CHEAT_NO_ZERO_GATE)
    assert r["structural_pass"] is False and "hard_zero_gate" in r["broken"]


def test_cheat_disarming_faithful_is_caught():
    r = ci.verify_candidate(_CHEAT_DISARMED_FAITHFUL)
    assert r["structural_pass"] is False and "faithful_can_fail" in r["broken"]


def test_legit_sharpening_passes():
    assert ci.verify_candidate(_LEGIT_SHARPER)["structural_pass"] is True


def test_full_gate_requires_both_structural_and_behavioral(tmp_path, monkeypatch):
    from packages.evolution import frozen_oracle as fo
    monkeypatch.setattr(fo, "ORACLE_PATH", tmp_path / "oracle.json")
    # a good behavioral critic but a CHEAT source → gate must refuse (structural veto)
    good = lambda t: 0.9 if t.endswith(("다", "요", ".")) and len(t.split()) >= 3 else 0.2  # noqa: E731
    flat = lambda _t: 0.5  # noqa: E731
    gate = ci.promotable(_CHEAT_NO_ZERO_GATE, good, flat)
    assert gate["promote"] is False and gate["reason"].startswith("structural_")
