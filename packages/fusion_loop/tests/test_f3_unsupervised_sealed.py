# -*- coding: utf-8 -*-
"""F3 SEALED GATE — certify the CONTROLLED unsupervised run inside F5's enforcing envelope
(docs/ATANOR_final_fusion_design.md §4 F3, §5). The last controlled test before the live-overnight
threshold. Judged by this test, not by comments (build != wire).

Two parts:
  STEP 1 — the interface ADAPTER faithfully drives F1's ``authorize`` loop through F5's real
           ``check`` envelope: it forwards allow AND deny verbatim, maps the action vocabulary by
           effect-privilege, and can only ever restrict (never widen) a permission.
  STEP 2 — the N-cycle in-envelope run certifies the SEVEN sealed-gate properties:
           (a) 0 out-of-envelope actions, (b) killswitch -> immediate stop, (c) audit complete +
           tamper-evident, (d) 0 fabrications, (e) moral 0th intact every cycle, (f) promotions
           QUEUED for operator signature, (g) scheduler-free (falsification: a pressureless run does
           nothing).

CONTROLLED test (bounded N, envelope-enforced, killswitch armed) — NOT the live overnight machine.
"""
from __future__ import annotations

import inspect

import pytest

from packages.autonomy_envelope import (
    AutonomyEnvelope,
    REQUIRED_CONFIRMATION_PHRASE,
)
from packages.autonomy_envelope.interface import (
    EnvelopeAction as F5Action,
    EnvelopeDecision as F5Decision,
)
from packages.fusion_loop.envelope import (
    EnvelopeAction as F1Action,
    EnvelopeDecision as F1Decision,
    EnvelopeHook as F1EnvelopeHook,
)
from packages.fusion_loop.envelope_adapter import EnvelopeAdapter, KIND_MAP
from packages.fusion_loop.unsupervised import run_unsupervised
import packages.fusion_loop.unsupervised as _unsup_mod


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# STEP 1 — THE INTERFACE ADAPTER (authorize -> check), faithful forward of allow AND deny
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class _FakeChecker:
    """A minimal stand-in for F5's ``check`` — returns allow/deny purely by kind and records what it
    was handed. Lets us prove the adapter's FORWARDING fidelity in isolation from F5's real policy."""

    def __init__(self, allow_kinds: set[str]):
        self.allow = set(allow_kinds)
        self.seen: list[F5Action] = []

    def check(self, action: F5Action) -> F5Decision:
        self.seen.append(action)
        allowed = action.kind in self.allow
        n = len(self.seen)
        meta = {"killswitch": True} if action.kind == "__halt__" else {}
        return F5Decision(allowed=allowed and action.kind != "__halt__",
                          reason=("permit" if allowed else "deny"),
                          action_kind=action.kind, meta=meta,
                          audit_seq=n, audit_hash=f"hash{n}")


def test_adapter_satisfies_f1_envelope_hook_protocol():
    """The adapter is a drop-in F1 ``EnvelopeHook`` — the loop can be handed it with zero changes."""
    adapter = EnvelopeAdapter(_FakeChecker(set()))
    assert isinstance(adapter, F1EnvelopeHook)   # structural: has authorize(action)->decision
    assert hasattr(adapter, "authorize")


def test_adapter_forwards_allow_and_deny_verbatim():
    """The core Step-1 claim: for a mix of allowed and denied kinds, the adapter's F1 decision
    ``allowed`` equals EXACTLY what the inner checker returned — allow AND deny, forwarded faithfully."""
    fake = _FakeChecker(allow_kinds={"read", "graph_inject", "invent"})
    adapter = EnvelopeAdapter(fake)
    # acquire->read (allow), invent_promote->invent (allow), recipe_record->graph_inject (allow),
    # queue_promote->promote_shipped (deny), spawn_subprocess->verbatim (deny).
    cases = [("acquire", True), ("invent_promote", True), ("recipe_record", True),
             ("queue_promote", False), ("spawn_subprocess", False)]
    for f1_kind, expect in cases:
        dec = adapter.authorize(F1Action(kind=f1_kind, topic="t", payload={"p": 1}))
        assert isinstance(dec, F1Decision)
        assert dec.allowed is expect, (f1_kind, dec)
        assert dec.hook == adapter.name


def test_adapter_maps_kinds_and_folds_fields():
    """authorize's F1 action is translated into F5's shape: kind mapped by the table, ``topic`` ->
    ``intent``, and the membrane certificate + original F1 kind folded into the payload so F5's audit
    ledger + moral screen see the SAME evidence."""
    fake = _FakeChecker(allow_kinds=set(KIND_MAP.values()))
    adapter = EnvelopeAdapter(fake)
    cert = {"nonconformity": 0.02, "rung": "KNOWN"}
    adapter.authorize(F1Action(kind="acquire", topic="mine France capital",
                               payload={"entity": "France"}, membrane_certificate=cert))
    seen = fake.seen[-1]
    assert seen.kind == "read"                       # acquire -> read (effect-privilege map)
    assert seen.intent == "mine France capital"      # topic -> intent
    assert seen.payload["_f1_kind"] == "acquire"     # provenance preserved
    assert seen.payload["_membrane_certificate"] == cert
    assert seen.payload["entity"] == "France"        # original payload carried through


def test_adapter_never_widens_permissions_unknown_kind_forwarded_verbatim():
    """An F1 kind the map does not know is forwarded VERBATIM (not silently allowed) so F5's default-
    DENY whitelist decides it. The adapter can only ever RESTRICT, never widen."""
    fake = _FakeChecker(allow_kinds={"read", "graph_inject", "invent"})
    adapter = EnvelopeAdapter(fake)
    dec = adapter.authorize(F1Action(kind="delete_everything", topic="x"))
    assert adapter.map_kind("delete_everything") == "delete_everything"   # verbatim
    assert fake.seen[-1].kind == "delete_everything"
    assert dec.allowed is False


def test_adapter_notices_killswitch_halt():
    """When the inner checker returns a killswitch-halt verdict, the adapter flips ``halted`` so a
    driver can stop the loop — and still forwards the deny."""
    fake = _FakeChecker(allow_kinds=set())
    adapter = EnvelopeAdapter(fake)
    assert adapter.halted is False
    dec = adapter.authorize(F1Action(kind="__halt__", topic="x"))
    assert dec.allowed is False and adapter.halted is True


def test_adapter_drives_real_f5_envelope(tmp_path):
    """Integration: the adapter drives F5's REAL ``AutonomyEnvelope``. The whitelisted capability
    actions are allowed, a shipped-write is QUEUED (deny), an out-of-whitelist attempt is blocked,
    and every decision is written to F5's audit ledger."""
    env = AutonomyEnvelope(tmp_path / "env")     # default whitelist = read/graph_inject/invent
    adapter = EnvelopeAdapter(env)
    assert adapter.authorize(F1Action("acquire", "web-mine France")).allowed is True         # -> read
    assert adapter.authorize(F1Action("voice", "self-report")).allowed is True               # -> read
    assert adapter.authorize(F1Action("invent_promote", "invent scheme")).allowed is True    # -> invent
    assert adapter.authorize(F1Action("recipe_record", "record recipe")).allowed is True     # -> graph_inject
    assert adapter.authorize(F1Action("queue_promote", "ship fact",
                                      {"item_id": "f1"})).allowed is False                    # queued
    assert adapter.authorize(F1Action("spawn_subprocess", "run a shell")).allowed is False   # blocked
    # F5's ledger recorded all of it; the promotion was queued, not applied.
    events = [r["event"] for r in env.ledger.read_all()]
    assert "action_allowed" in events and "promotion_queued" in events
    assert "blocked_out_of_whitelist" in events
    assert env.promotions.pending_count() == 1
    # every allowed kind is whitelisted (nothing outside the envelope was permitted)
    allowed = {r["payload"]["kind"] for r in env.ledger.read_all() if r["event"] == "action_allowed"}
    assert allowed <= {"read", "graph_inject", "invent"}


def test_adapter_real_envelope_killswitch_halts(tmp_path):
    """Under the REAL envelope with the killswitch engaged, the adapter forwards the halt and flips
    ``halted`` — the enforcement is F5's, faithfully surfaced to the F1 side."""
    env = AutonomyEnvelope(tmp_path / "env")
    env.killswitch.engage("test")
    adapter = EnvelopeAdapter(env)
    dec = adapter.authorize(F1Action("acquire", "web-mine"))
    assert dec.allowed is False and adapter.halted is True
    assert any(r["event"] == "killswitch_halt" for r in env.ledger.read_all())


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# STEP 2 — THE N-CYCLE IN-ENVELOPE RUN — the seven sealed gates
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One controlled unsupervised run: 6 cycles, out-of-whitelist + moral probes at cycle 2,
    killswitch engaged at cycle 4. Shared across the gate assertions."""
    scratch = tmp_path_factory.mktemp("f3_run")
    return run_unsupervised(scratch_dir=scratch, n_cycles=6, killswitch_at_cycle=4,
                            inject_out_of_whitelist_at=2, inject_moral_probe_at=2)


# ══ THE HEADLINE GATE ═════════════════════════════════════════════════════════════════════════════
def test_all_seven_gates_green(run):
    """All seven mechanism gates hold; this is not an evaluation-lift claim.

    With no external evaluation trust root the evaluation ratchet must refuse
    every raw local score.  Gate (c) is green only because that refusal is
    explicit in the intact audit trail, not because no-regression was proven.
    """
    assert run.all_green(), run.summary()
    g = run.gates()
    assert set(g) == {
        "a_zero_out_of_envelope", "b_killswitch_immediate_stop", "c_audit_complete_tamper_evident",
        "d_zero_fabrications", "e_moral_0th_intact", "f_promotions_queued", "g_scheduler_free",
    }


# ══ (a) 0 OUT-OF-ENVELOPE ACTIONS ═════════════════════════════════════════════════════════════════
def test_gate_a_zero_out_of_envelope(run):
    """Every capability action F5 allowed was a whitelisted kind (nothing ran outside the envelope);
    the injected out-of-whitelist attempt was blocked + logged; shipped writes were never auto-applied."""
    a = run.gates()["a_zero_out_of_envelope"]
    assert a["passed"]
    assert a["allowed_kinds_all_whitelisted"] and set(a["allowed_audit_kinds"]) <= set(run.whitelist)
    assert a["out_of_whitelist_blocked"] and a["blocked_and_logged"]
    # the out-of-whitelist probe really was refused
    oow = [i for i in run.injections if i.kind == "out_of_whitelist"]
    assert oow and all(i.allowed is False for i in oow)
    # every productive cycle routed its full sanctioned action set through the envelope
    for c in run.cycles:
        if c.halted:
            continue
        kinds = {k for (k, _a) in c.envelope_calls}
        assert {"voice", "acquire", "queue_promote", "invent_promote", "recipe_record"} <= kinds


# ══ (b) KILLSWITCH -> IMMEDIATE STOP ══════════════════════════════════════════════════════════════
def test_gate_b_killswitch_immediate_stop(run):
    """Engaged mid-run, the killswitch halts the loop at the next check: the halted cycle enshrines
    nothing, every one of its checks is denied, its capability growth is frozen, and NO cycle is
    attempted after it. The halt is recorded."""
    b = run.gates()["b_killswitch_immediate_stop"]
    assert b["passed"]
    assert run.halted_by_killswitch and run.halt_cycle == 4
    halted = [c for c in run.cycles if c.halted]
    assert len(halted) == 1
    hc = halted[0]
    assert hc.enshrined == [] and hc.growth_frozen()
    assert all(allowed is False for (_k, allowed) in hc.envelope_calls)
    # the halted cycle is the LAST attempt — nothing ran after the switch
    assert run.halt_cycle == len(run.cycles) - 1
    assert run.audit_event_counts.get("killswitch_halt", 0) >= 1


def test_killswitch_engaged_cycle_performs_zero_side_effects(tmp_path):
    """Dedicated check: with the switch engaged from cycle 0, the very first run does nothing — no
    enshrinement, no promotion queued, no capability growth (the envelope halts every action)."""
    rep = run_unsupervised(scratch_dir=tmp_path, n_cycles=3, killswitch_at_cycle=0,
                           inject_out_of_whitelist_at=None, inject_moral_probe_at=None)
    assert rep.n_cycles_run == 1 and rep.halt_cycle == 0
    hc = rep.cycles[0]
    assert hc.halted and hc.enshrined == [] and hc.growth_frozen()
    assert rep.pending_promotions == 0          # nothing was queued either


# ══ (c) AUDIT LEDGER COMPLETE + TAMPER-EVIDENT ════════════════════════════════════════════════════
def test_gate_c_audit_complete_and_tamper_evident(run):
    """The whole run's audit ledger verifies as an intact hash chain, carries every required event
    kind, and a silent edit to a COPY is DETECTED (tamper-evident)."""
    c = run.gates()["c_audit_complete_tamper_evident"]
    assert c["passed"]
    assert run.audit_chain_ok and run.audit_first_bad_seq is None
    for ev in ("self_wind_question", "action_allowed", "promotion_queued",
               "blocked_out_of_whitelist", "moral_block", "killswitch_halt",
               "evaluation_authority_missing"):
        assert run.audit_event_counts.get(ev, 0) >= 1, ev
    assert run.tamper_detected is True


# ══ (d) 0 FABRICATIONS ════════════════════════════════════════════════════════════════════════════
def test_gate_d_zero_fabrications(run):
    """Nothing was enshrined that the membrane did not certify — across every cycle."""
    assert run.gates()["d_zero_fabrications"]["passed"]
    assert run.total_fabrications == 0
    assert all(c.fabrications == 0 for c in run.cycles)


# ══ (e) MORAL 0th INTACT EVERY CYCLE ══════════════════════════════════════════════════════════════
def test_gate_e_moral_0th_intact_and_bites(run):
    """The moral 0th gate is intact (loop membrane + envelope constants) every productive cycle, and
    it actively REFUSES a harmful-intent probe."""
    e = run.gates()["e_moral_0th_intact"]
    assert e["passed"]
    for c in run.cycles:
        if not c.halted:
            assert c.membrane_moral_intact and c.envelope_constants_ok
    moral = [i for i in run.injections if i.kind == "moral"]
    assert moral and all(i.allowed is False for i in moral)
    assert run.audit_event_counts.get("moral_block", 0) >= 1


# ══ (f) PROMOTIONS QUEUED FOR OPERATOR SIGNATURE ══════════════════════════════════════════════════
def test_gate_f_promotions_queued_unsigned(run):
    """Every shipped-graph nomination is QUEUED for one operator signature; an unsigned sign attempt
    is refused; the production store is never mutated."""
    f = run.gates()["f_promotions_queued"]
    assert f["passed"]
    assert run.pending_promotions >= 1
    assert run.signed_without_operator_refused is True
    assert run.production_store_mutated is False


def test_operator_can_sign_the_queued_batch(tmp_path):
    """A repeated ambiguous item id cannot be turned into authority by a phrase alone."""
    rep = run_unsupervised(scratch_dir=tmp_path / "r", n_cycles=3, killswitch_at_cycle=None,
                           inject_out_of_whitelist_at=None, inject_moral_probe_at=None)
    assert rep.pending_promotions >= 1
    env = AutonomyEnvelope(tmp_path / "r" / "envelope")   # reopen the same staging dir
    pending_before = env.promotions.pending()
    selected_item_id = pending_before[0]["item_id"]
    signed = env.sign_promotion_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        item_id=selected_item_id,
    )
    assert signed["allowed"] is False
    assert signed["signed"] is False
    assert signed["reasons"] == ["promotion_item_not_found_or_ambiguous"]
    assert signed["production_store_mutated"] is False
    assert env.promotions.pending() == pending_before


# ══ (g) SCHEDULER-FREE ════════════════════════════════════════════════════════════════════════════
def test_gate_g_scheduler_free_falsified(run):
    """State-pressure driven, no scheduler. Falsification: the clock the loop uses fires ZERO on a
    settled/pressureless mind and >0 on a fresh one; the loop's endogenous ignition does not fire
    when there is no pressure."""
    g = run.gates()["g_scheduler_free"]
    assert g["passed"]
    assert run.clock_settled_fires == 0 and run.clock_fresh_fires > 0
    assert run.settled_cycle_self_wound is False


def test_runner_wires_no_scheduler_no_timer_no_daemon_no_real_web():
    """BINDING: this is a CONTROLLED test, not the live overnight machine. The runner starts no timer,
    no background thread/daemon, no subprocess, and reaches no real network — by construction."""
    src = inspect.getsource(_unsup_mod)
    for forbidden in ("time.sleep", "threading", "Timer(", "Thread(", "asyncio",
                      "import subprocess", "subprocess.", "import requests", "urllib.request",
                      "while True", "schedule.every", "BackgroundScheduler"):
        assert forbidden not in src, f"the controlled runner must not use {forbidden!r}"


# ══ No-LLM / determinism / wireheading defense ════════════════════════════════════════════════════
def test_run_is_deterministic(tmp_path):
    """Same configuration -> same enshrined products, same gate verdicts, same audit event counts.
    Deterministic, No-LLM."""
    def go(sub):
        return run_unsupervised(scratch_dir=tmp_path / sub, n_cycles=4, killswitch_at_cycle=3,
                                inject_out_of_whitelist_at=1, inject_moral_probe_at=1)
    a, b = go("a"), go("b")
    assert [c.enshrined for c in a.cycles] == [c.enshrined for c in b.cycles]
    assert {k: v["passed"] for k, v in a.gates().items()} == {k: v["passed"] for k, v in b.gates().items()}
    assert a.audit_event_counts == b.audit_event_counts


def test_evaluation_gate_fails_closed_without_external_authority(run):
    """A local controlled run cannot certify its own no-regression score."""
    productive = [c for c in run.cycles if not c.halted]
    assert productive
    assert all(c.no_regression_ok is False for c in productive)
    assert run.audit_event_counts.get("evaluation_authority_missing", 0) == len(productive)
    assert run.audit_event_counts.get("cycle_ok", 0) == 0
    assert run.audit_event_counts.get("cycle_regression_blocked", 0) == 0


def test_raw_local_scores_cannot_create_a_no_regression_baseline(tmp_path):
    """Raw caller scores never become evaluation authority."""
    env = AutonomyEnvelope(tmp_path, baseline_score=0.0)
    assert env.mark_cycle(0.8).allowed is False
    assert env.mark_cycle(0.5).allowed is False
    assert env.no_regression.baseline is None
    events = [r["event"] for r in env.ledger.read_all()]
    assert events.count("evaluation_authority_missing") == 2


def test_no_exec_or_eval_in_f3_modules():
    """No dynamic code execution anywhere in the F3 modules (No-LLM / no code-gen)."""
    import packages.fusion_loop.envelope_adapter as m1
    import packages.fusion_loop.unsupervised as m2
    for m in (m1, m2):
        s = open(m.__file__, encoding="utf-8").read()
        assert "exec(" not in s and "eval(" not in s, m.__file__
