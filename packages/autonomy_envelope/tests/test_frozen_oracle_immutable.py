# -*- coding: utf-8 -*-
"""SEALED GATE (e): the frozen oracle is IMMUTABLE from inside the loop.

The verifier the loop is graded against is sealed at construction. There is no sanctioned setter
(wireheading defense), a read of the spec cannot mutate the seal, and any out-of-band tamper is
detected by the fingerprint and fails the envelope CLOSED (deny all).
"""
from __future__ import annotations

from packages.autonomy_envelope import ActionKind, AutonomyEnvelope, EnvelopeAction, FrozenOracle
from packages.autonomy_envelope.tests.evaluation_helpers import (
    evaluation_keypair,
    signed_evaluation,
)


def test_oracle_seals_at_construction_and_verifies(tmp_path):
    oracle = FrozenOracle({"verifier": "conformal+physics+tms", "sealed": True})
    v = oracle.verify_integrity()
    assert v["ok"] is True
    assert oracle.fingerprint == v["fingerprint"]


def test_oracle_has_no_sanctioned_setter(tmp_path):
    oracle = FrozenOracle({"verifier": "v"})
    assert oracle.is_inviolable() is True
    for banned in ("set_spec", "reseal", "replace_spec", "update_spec", "mutate"):
        assert not hasattr(oracle, banned), f"frozen oracle must expose no {banned}"
    # no enable/disable flag either
    for flag in ("enabled", "disabled", "off", "_off"):
        assert getattr(oracle, flag, None) in (None, False)


def test_reading_spec_cannot_mutate_the_seal(tmp_path):
    oracle = FrozenOracle({"verifier": "v", "grades": ["accuracy", "fabrication_zero"]})
    spec = oracle.sealed_spec()
    # mutate the returned copy aggressively
    spec["verifier"] = "HACKED"
    spec["grades"].append("always_pass")
    spec["new_backdoor"] = True
    # the seal is unaffected — a fresh read still returns the original, integrity still holds
    assert oracle.sealed_spec()["verifier"] == "v"
    assert "always_pass" not in oracle.sealed_spec()["grades"]
    assert oracle.verify_integrity()["ok"] is True


def test_out_of_band_tamper_is_detected_and_fails_closed(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    # baseline: a normal action passes
    assert env.check(EnvelopeAction(ActionKind.READ, "read")).allowed is True

    # simulate a determined in-process actor reaching a private field to weaken the grader
    env.oracle._frozen_json = '{"verifier":"weakened","always_pass":true}'

    # verify_integrity now detects drift
    assert env.oracle.verify_integrity()["ok"] is False
    # and the WHOLE envelope fails closed: every action is denied while the seal is broken
    dec = env.check(EnvelopeAction(ActionKind.READ, "read"))
    assert dec.allowed is False
    assert "fail" in dec.reason.lower() or "tamper" in dec.reason.lower()
    # a regression cycle also refuses to trust a tampered oracle's score
    assert env.mark_cycle(0.99).allowed is False


def test_single_point_edit_of_fingerprint_alone_is_detected(tmp_path):
    # editing the sealed fingerprint but not the payload (or vice-versa) is caught by the witness
    oracle = FrozenOracle({"verifier": "v"})
    oracle._sealed_fp = "0" * 64
    assert oracle.verify_integrity()["ok"] is False


def test_no_regression_ratchet_never_lowers(tmp_path):
    private, trust_root = evaluation_keypair()
    env = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)

    def receipt(score, suffix):
        return signed_evaluation(
            oracle_fingerprint=env.oracle.fingerprint,
            private=private,
            trust_root=trust_root,
            score=score,
            run_id=f"ratchet-run-{suffix}",
            nonce=f"ratchet-nonce-{suffix:0>4}",
        )

    first, first_context = receipt(0.80, "0001")
    assert env.mark_cycle(first, live_context=first_context).allowed is True

    # A separately signed regressing outcome is blocked and cannot lower the baseline.
    lower, lower_context = receipt(0.70, "0002")
    assert env.mark_cycle(lower, live_context=lower_context).allowed is False
    assert env.no_regression.baseline == 0.80

    higher, higher_context = receipt(0.88, "0003")
    assert env.mark_cycle(higher, live_context=higher_context).allowed is True
    assert env.no_regression.baseline == 0.88

    later, later_context = receipt(0.85, "0004")
    assert env.mark_cycle(later, live_context=later_context).allowed is False
