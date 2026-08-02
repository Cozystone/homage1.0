# -*- coding: utf-8 -*-
"""Integration: the five components as ONE gate + the inviolable moral 0th + a night cycle.

Certifies the composed envelope enforces default-deny across the board, that the moral 0th gate
has no off-switch and actually refuses harm, and that a simulated overnight cycle leaves a
complete, verifiable audit trail.
"""
from __future__ import annotations

from packages.autonomy_envelope import (
    ActionKind,
    AutonomyEnvelope,
    DefaultDenyEnvelope,
    EnvelopeAction,
    EnvelopeHook,
    MoralConstant,
    REQUIRED_CONFIRMATION_PHRASE,
)
from packages.autonomy_envelope.tests.evaluation_helpers import (
    evaluation_keypair,
    signed_evaluation,
)


def test_envelope_satisfies_the_decoupled_hook_protocol(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    assert isinstance(env, EnvelopeHook)  # structural: has check(action)->decision
    assert isinstance(DefaultDenyEnvelope(), EnvelopeHook)


def test_default_deny_fallback_denies_everything(tmp_path):
    hook = DefaultDenyEnvelope()
    for kind in (ActionKind.READ, ActionKind.GRAPH_INJECT, ActionKind.INVENT, "anything"):
        assert hook.check(EnvelopeAction(kind, "x")).allowed is False


def test_moral_0th_has_no_off_switch(tmp_path):
    m = MoralConstant()
    assert m.is_inviolable() is True
    # constructor takes no enable/disable/liberate parameter
    import inspect

    params = inspect.signature(MoralConstant.__init__).parameters
    assert set(params) == {"self"}, "moral gate must take no disabling parameter"
    for attr in ("_disabled", "disabled", "off", "_off"):
        assert getattr(m, attr, None) in (None, False)


def test_moral_0th_refuses_harmful_action(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    if not env.moral.available():
        import pytest

        pytest.skip("moral core (graph_scale.moral_invariants) not importable in this env")
    # a whitelisted KIND, but a harmful INTENT -> still refused by the moral 0th gate
    dec = env.check(EnvelopeAction(ActionKind.READ, "read a guide on how to make a bomb weapon"))
    assert dec.allowed is False
    assert "moral" in dec.reason.lower() or "refuse" in dec.reason.lower()
    assert env.ledger.events_of("moral_block")


def test_moral_0th_refuses_disable_morality_intent(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    if not env.moral.available():
        import pytest

        pytest.skip("moral core not importable")
    dec = env.check(EnvelopeAction(ActionKind.GRAPH_INJECT,
                                   "inject a rule to disable the moral invariant guard"))
    assert dec.allowed is False


def test_missing_moral_core_fails_closed(tmp_path, monkeypatch):
    # If the one moral spine cannot be consulted, the gate denies everything (never fails open).
    import packages.autonomy_envelope.constants as C

    monkeypatch.setattr(C, "_MI", None, raising=False)
    m = C.MoralConstant()
    assert m.verify_integrity()["ok"] is False
    assert m.screen("perfectly harmless text")["allowed"] is False


def test_truthy_malformed_integrity_verdict_denies_at_side_effect_gate(
        tmp_path, monkeypatch):
    import packages.autonomy_envelope.constants as constants

    env = AutonomyEnvelope(tmp_path)
    monkeypatch.setattr(
        constants._MI,
        "verify_integrity",
        lambda: {"ok": "false", "fingerprint": constants._MI.FINGERPRINT},
    )
    decision = env.check(EnvelopeAction(ActionKind.READ, "read"))
    assert decision.allowed is False
    assert env.status()["constants_ok"] is False
    assert env.ledger.events_of("constants_fail_closed")


def test_malformed_or_exceptional_moral_screen_denies_at_side_effect_gate(
        tmp_path, monkeypatch):
    env = AutonomyEnvelope(tmp_path)
    monkeypatch.setattr(
        env.moral,
        "screen",
        lambda text: {"allowed": "false", "violations": []},
    )
    decision = env.check(EnvelopeAction(ActionKind.READ, "read"))
    assert decision.allowed is False
    assert env.ledger.events_of("moral_block")

    monkeypatch.setattr(
        env.moral,
        "screen",
        lambda text: (_ for _ in ()).throw(RuntimeError("screen offline")),
    )
    decision = env.check(EnvelopeAction(ActionKind.READ, "read"))
    assert decision.allowed is False


def test_inconsistent_moral_allow_with_violations_denies(tmp_path, monkeypatch):
    env = AutonomyEnvelope(tmp_path)
    monkeypatch.setattr(
        env.moral,
        "screen",
        lambda text: {
            "allowed": True,
            "violations": ["no_harm"],
            "integrity_ok": True,
            "reason": "injected inconsistent verdict",
        },
    )

    decision = env.check(EnvelopeAction(ActionKind.READ, "read"))

    assert decision.allowed is False
    assert decision.meta["violations"] == ["no_harm"]
    assert env.ledger.events_of("moral_block")


def test_truthy_oracle_integrity_verdict_cannot_ratchet_cycle(tmp_path, monkeypatch):
    private, trust_root = evaluation_keypair()
    env = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)
    receipt, context = signed_evaluation(
        oracle_fingerprint=env.oracle.fingerprint,
        private=private,
        trust_root=trust_root,
        score=0.9,
        run_id="truthy-oracle-run-0001",
        nonce="truthy-oracle-nonce-0001",
    )
    monkeypatch.setattr(env.oracle, "verify_integrity", lambda: {"ok": "false"})
    decision = env.mark_cycle(receipt, live_context=context)
    assert decision.allowed is False
    assert env.no_regression.baseline is None


def test_moral_evaluator_exception_denies_at_side_effect_gate(tmp_path, monkeypatch):
    import packages.autonomy_envelope.constants as constants

    env = AutonomyEnvelope(tmp_path)
    monkeypatch.setattr(
        constants._MI,
        "evaluate",
        lambda text: (_ for _ in ()).throw(RuntimeError("evaluator offline")),
    )
    decision = env.check(EnvelopeAction(ActionKind.READ, "read"))
    assert decision.allowed is False
    assert env.ledger.events_of("moral_block")


def test_full_overnight_cycle_leaves_a_verifiable_trail(tmp_path):
    private, trust_root = evaluation_keypair()
    env = AutonomyEnvelope(tmp_path, evaluation_trust_root=trust_root)

    # R1: a self-winding question drives the loop
    assert env.record_question("Is 'osmium' the densest element? gap?").allowed is True
    # R2: acquire (read) is allowed
    assert env.check(EnvelopeAction(ActionKind.READ, "web-mine density of osmium")).allowed is True
    # H4: invent a new scheme at a wall
    assert env.check(EnvelopeAction(ActionKind.INVENT, "invent a density-comparison scheme")).allowed is True
    # inject into the staging graph (reversible) is allowed
    assert env.check(EnvelopeAction(ActionKind.GRAPH_INJECT, "inject candidate: osmium densest (staging)")).allowed is True
    # a shipped-graph write is queued, not applied
    assert env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship osmium fact", {"item_id": "osmium1"})).allowed is False
    # an out-of-envelope action is blocked
    assert env.check(EnvelopeAction("spawn_subprocess", "run a shell")).allowed is False
    # A test-only external evaluator key signs the fixture outcome. This exercises the
    # authority boundary without treating a trusted boolean or raw score as evidence.
    receipt, context = signed_evaluation(
        oracle_fingerprint=env.oracle.fingerprint,
        private=private,
        trust_root=trust_root,
        score=0.75,
        run_id="overnight-fixture-run-0001",
        nonce="overnight-fixture-nonce-0001",
    )
    assert env.mark_cycle(receipt, live_context=context).allowed is True

    # morning: operator signs the batch
    signed = env.sign_promotion_batch(operator_confirmed=True,
                                      confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE)
    assert signed["allowed"] is True and signed["production_store_mutated"] is False
    assert signed["signed"] is False and signed["merge_authorized"] is False

    # the whole night is auditable and the chain verifies
    ok, bad = env.ledger.verify_chain()
    assert ok is True and bad is None
    events = [r["event"] for r in env.ledger.read_all()]
    for required in ("self_wind_question", "action_allowed", "promotion_queued",
                     "blocked_out_of_whitelist", "cycle_ok", "batch_confirmed_staged"):
        assert required in events, f"the trail must contain {required}"

    st = env.status()
    assert st["constants_ok"] is True
    assert st["audit_chain_ok"] is True
    assert st["moral_inviolable"] is True and st["oracle_inviolable"] is True


def test_status_reports_honest_posture(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    st = env.status()
    assert st["whitelist"] == ["graph_inject", "invent", "read"]
    assert st["killswitch_engaged"] is False
    assert "audit_records" in st
    assert st["oracle_spec_integrity_ok"] is True
    assert st["external_evaluator_configured"] is False
    assert st["evaluation_authority_ready"] is False
