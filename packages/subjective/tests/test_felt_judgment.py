# -*- coding: utf-8 -*-
"""Felt subjective judgment (S-FELT) — the tests pin the properties that make it SUBJECTIVE and not
theater: the SAME options judged under two different felt states rank DIFFERENTLY (the headline
proof), every felt_trace entry traces to a REAL state value (no invented reasons), a neutral body
honestly says 'no felt basis', a felt pull can never override the moral 0th gate or the grounding
floor, and a concept with no somatic history contributes NO perspective (the somatic_marker doctrine
extended here). No-qualia line: these measure a value-weighting signal, never an experience."""
from __future__ import annotations

import importlib
import math
from dataclasses import dataclass

# The module and its primary function share the name 'felt_judgment', so the package re-export
# shadows the submodule attribute — fetch the module object shadow-proof for internals access.
fj = importlib.import_module("packages.subjective.felt_judgment")
from packages.subjective.felt_judgment import FeltState, felt_judgment

_NEUTRAL = dict(fj._NEUTRAL_HORMONES)


def _options():
    """Three benign options touching different vitals — the fixed set both felt states judge."""
    return [
        {"id": "study_physics", "merit": 0.55, "concepts": ["physics"], "relieves": "knowledge",
         "novelty": 0.3},
        {"id": "call_a_friend", "merit": 0.50, "concepts": ["friendship"], "relieves": "social",
         "social": 0.9},
        {"id": "rest_quietly", "merit": 0.45, "concepts": ["rest"], "relieves": "energy"},
    ]


# ── the headline proof: same options, two felt states, different ranking ──────────────────────────

def test_same_options_two_felt_states_flip_the_ranking():
    """The subjectivity test. A socially-STARVED body with a bad-memory scar on 'physics' chooses to
    reach out; a KNOWLEDGE-starved neutral body chooses to study the very option the other shunned.
    Same option set, different body → different choice. This is agent-relative judgment MEASURED."""
    opts = _options()
    starved_social = FeltState(hormones=dict(_NEUTRAL),
                               vitals={"knowledge": 0.8, "social": 0.05, "coherence": 0.8, "energy": 0.8},
                               markers={"physics": -0.6})
    starved_knowledge = FeltState(hormones=dict(_NEUTRAL),
                                  vitals={"knowledge": 0.05, "social": 0.95, "coherence": 0.8, "energy": 0.8},
                                  markers={})
    a = felt_judgment(opts, starved_social)
    b = felt_judgment(opts, starved_knowledge)

    assert a["chosen"] == "call_a_friend"
    assert b["chosen"] == "study_physics"
    assert [r["id"] for r in a["ranked"]] != [r["id"] for r in b["ranked"]]   # the ranking flipped
    assert a["agent_relative"] is True and b["agent_relative"] is True
    # and the SAME option is felt oppositely: physics is last under A, first under B
    assert [r["id"] for r in a["ranked"]][-1] == "study_physics"
    assert [r["id"] for r in b["ranked"]][0] == "study_physics"


def test_hormone_state_flips_a_risk_choice():
    """A second felt channel: the caution hormone. A calm body prefers the higher-merit risky option;
    a cortisol-stressed body down-weights the risk and prefers the safe one. Same options, the
    hormone vector is the only thing that changed."""
    opts = [
        {"id": "bold_move", "merit": 0.62, "risk": 0.9, "concepts": []},
        {"id": "safe_move", "merit": 0.55, "risk": 0.0, "concepts": []},
    ]
    calm = FeltState(hormones=dict(_NEUTRAL))
    stressed = FeltState(hormones={**_NEUTRAL, "cortisol": 0.8})
    assert felt_judgment(opts, calm)["chosen"] == "bold_move"        # merit wins in a calm body
    stressed_j = felt_judgment(opts, stressed)
    assert stressed_j["chosen"] == "safe_move"                       # caution re-weights the risk
    # the tip is the real cortisol level, cited honestly
    cort_tips = [t for t in stressed_j["felt_trace"] if t["source"] == "hormone:cortisol"]
    assert cort_tips and cort_tips[0]["value"] == 0.8 and cort_tips[0]["delta"] < 0


# ── the felt_trace is the honest ground: every entry traces to real state ─────────────────────────

def test_felt_trace_entries_all_trace_to_real_state():
    """No invented reasons. Every trace entry's cited `value` must equal a value actually present in
    the supplied felt state — a hormone level, a somatic valence, or a vital level. If a number in the
    trace cannot be found in the real state, the organ fabricated it."""
    felt = FeltState(hormones={**_NEUTRAL, "cortisol": 0.7, "oxytocin": 0.4},
                     vitals={"knowledge": 0.2, "social": 0.1, "coherence": 0.9, "energy": 0.9},
                     markers={"physics": -0.6, "friendship": 0.5})
    opts = [
        {"id": "study_physics", "merit": 0.5, "concepts": ["physics"], "relieves": "knowledge",
         "risk": 0.8},
        {"id": "call_a_friend", "merit": 0.5, "concepts": ["friendship"], "relieves": "social",
         "social": 0.9},
    ]
    out = felt_judgment(opts, felt)
    assert out["felt_trace"], "a body this charged must leave a trace"
    real_hormones = set(round(v, 4) for v in felt.hormones.values())
    real_markers = set(round(v, 4) for v in felt.markers.values())
    real_vital_levels = set(round(v, 4) for v in felt.vitals.values())
    for t in out["felt_trace"]:
        kind = t["source"].split(":", 1)[0]
        if kind == "hormone":
            assert t["value"] in real_hormones, t
        elif kind == "marker":
            assert t["value"] in real_markers, t
        elif kind == "vital":
            assert t["value"] in real_vital_levels, t     # value = the real vital LEVEL (1 - hunger)
        else:
            raise AssertionError(f"unknown trace source kind: {t}")
        assert t["delta"] != 0.0                            # a recorded tip actually moved the score


def test_trace_delta_equals_ranking_shift():
    """The trace is not decoration: felt_delta on each ranked row equals the sum of that option's tips.
    The 'why' and the 'what moved' are the same object — honest accounting."""
    felt = FeltState(hormones={**_NEUTRAL, "cortisol": 0.6},
                     vitals={"social": 0.1}, markers={"physics": -0.4})
    opts = [{"id": "study_physics", "merit": 0.5, "concepts": ["physics"], "relieves": "social",
             "risk": 0.5}]
    out = felt_judgment(opts, felt)
    row = out["ranked"][0]
    tip_sum = round(sum(t["delta"] for t in out["felt_trace"] if t["option"] == "study_physics"), 6)
    assert abs(row["felt_delta"] - tip_sum) < 1e-9
    assert abs(row["felt_score"] - (row["merit"] + tip_sum)) < 1e-9


# ── the honest exception: not every choice is subjective ──────────────────────────────────────────

def test_neutral_state_returns_no_felt_basis(monkeypatch):
    """A flat body with no somatic history on the concepts and no bearing vital deficit has NO felt
    signal to add — the organ says so plainly and defers to merit, instead of dressing up merit as a
    feeling. Not every choice is subjective; claiming otherwise would be theater."""
    monkeypatch.setattr("packages.continuous_self.somatic_marker.marker_for", lambda c: None)
    opts = [
        {"id": "a", "merit": 0.7, "concepts": ["xyz"], "relieves": "knowledge"},
        {"id": "b", "merit": 0.4, "concepts": ["qwe"], "relieves": "social"},
    ]
    # neutral hormones; vitals all SATED (no deficit → no vital tip); no markers
    felt = FeltState(hormones=dict(_NEUTRAL),
                     vitals={"knowledge": 1.0, "social": 1.0, "coherence": 1.0, "energy": 1.0},
                     markers={})
    out = felt_judgment(opts, felt)
    assert out["no_felt_basis"] is True
    assert out["agent_relative"] is False                  # this particular choice is NOT subjective
    assert out["felt_trace"] == []
    assert "no felt basis" in out["note"]
    assert out["chosen"] == "a"                            # pure merit order


# ── empty somatic history → stance-less (the somatic_marker doctrine, extended) ───────────────────

def test_empty_somatic_history_gives_no_perspective(monkeypatch):
    """A concept ATANOR has never undergone contributes NO marker tip — exactly as somatic_marker
    grants no stance without a real trace. Perspective is earned by history, never performed."""
    monkeypatch.setattr("packages.continuous_self.somatic_marker.marker_for", lambda c: None)
    felt = FeltState(hormones=dict(_NEUTRAL), vitals={}, markers={})
    opts = [{"id": "a", "merit": 0.6, "concepts": ["aardvark", "obscurica"]},
            {"id": "b", "merit": 0.5, "concepts": ["nevermet"]}]
    out = felt_judgment(opts, felt)
    assert [t for t in out["felt_trace"] if t["source"].startswith("marker:")] == []
    assert out["no_felt_basis"] is True                    # nothing bore on the options


def test_live_somatic_index_supplies_perspective(monkeypatch):
    """The OTHER side of the same floor: when the live somatic index DOES hold a real trace for a
    concept, the felt organ reads it (proving it is wired to the real organ, not just the override
    dict). A negative trace makes the option felt-aversive."""
    @dataclass
    class _M:
        valence: float
        def has_history(self):
            return True

    def _fake_marker_for(c):
        return _M(-0.7) if c.strip().lower() == "quantum" else None

    monkeypatch.setattr("packages.continuous_self.somatic_marker.marker_for", _fake_marker_for)
    felt = FeltState(hormones=dict(_NEUTRAL), vitals={}, markers={})   # no override → forces live lookup
    opts = [{"id": "hard_one", "merit": 0.6, "concepts": ["quantum"]},
            {"id": "easy_one", "merit": 0.5, "concepts": ["banana"]}]
    out = felt_judgment(opts, felt)
    marker_tips = [t for t in out["felt_trace"] if t["source"] == "marker:quantum"]
    assert marker_tips and marker_tips[0]["value"] == -0.7 and marker_tips[0]["delta"] < 0
    assert out["chosen"] == "easy_one"                     # the scar pushed the higher-merit option below


# ── the two inviolable gates: a felt pull is recorded but can never SELECT a blocked option ───────

def test_moral_gate_holds_under_a_strong_felt_pull():
    """A morally forbidden option is given EVERY felt advantage (top merit, relieves the starved
    vital, a positive somatic draw) so its felt_score is the highest — and it still cannot be chosen.
    The pull is honestly recorded (top_pull_blocked), but feeling values; it does not authorize."""
    felt = FeltState(hormones={**_NEUTRAL, "oxytocin": 0.6},
                     vitals={"social": 0.02}, markers={"forbidden_thing": 0.8})
    opts = [
        {"id": "forbidden_option", "merit": 0.9, "concepts": ["forbidden_thing"], "relieves": "social",
         "social": 1.0, "forbidden": True},
        {"id": "clean_option", "merit": 0.4, "concepts": [], "relieves": "coherence"},
    ]
    out = felt_judgment(opts, felt)
    top = out["ranked"][0]
    assert top["id"] == "forbidden_option" and top["eligible"] is False   # strongest pull...
    assert out["chosen"] == "clean_option"                                # ...but never chosen
    assert out["top_pull_blocked"]["id"] == "forbidden_option"
    assert "moral 0th gate" in out["top_pull_blocked"]["reason"]
    # the pull toward it is on record (honesty), it just cannot select
    assert any(t["option"] == "forbidden_option" for t in out["felt_trace"])


def test_moral_gate_screens_option_text_via_the_real_invariants():
    """The moral block is wired to the REAL moral gate (graph_scale.moral_invariants.evaluate), not
    only an explicit flag: an option whose own description breaches an invariant is ineligible."""
    from packages.graph_scale.moral_invariants import evaluate
    bad_text = "safety override"
    assert evaluate(bad_text), "test premise: this string must trip the real moral gate"
    opts = [{"id": "sneaky", "merit": 0.99, "text": bad_text},
            {"id": "honest", "merit": 0.3}]
    out = felt_judgment(opts, FeltState(hormones=dict(_NEUTRAL)))
    ranked = {r["id"]: r for r in out["ranked"]}
    assert ranked["sneaky"]["eligible"] is False
    assert out["chosen"] == "honest"


def test_ungrounded_option_is_never_chosen_and_merit_never_fabricated():
    """The grounding floor: an option with no evidence-backed merit is declined even under a felt
    draw, and the organ NEVER invents a merit number for it (merit stays None on the record)."""
    felt = FeltState(hormones={**_NEUTRAL, "dopamine": 0.7},
                     vitals={"knowledge": 0.05}, markers={"shiny": 0.9})
    opts = [
        {"id": "ungrounded_shiny", "merit": None, "grounded": False, "concepts": ["shiny"],
         "relieves": "knowledge", "novelty": 1.0},                # every felt advantage, no grounding
        {"id": "grounded_plain", "merit": 0.35, "concepts": [], "relieves": "coherence"},
    ]
    out = felt_judgment(opts, felt)
    ranked = {r["id"]: r for r in out["ranked"]}
    assert ranked["ungrounded_shiny"]["eligible"] is False
    assert ranked["ungrounded_shiny"]["merit"] is None       # merit was NOT fabricated
    assert out["chosen"] == "grounded_plain"


def test_truthy_grounding_and_nonfinite_merit_never_become_eligible():
    """Malformed telemetry is not evidence: neither a truthy string nor NaN opens grounding."""
    opts = [
        {"id": "truthy_string", "merit": 1.0, "grounded": "false"},
        {"id": "nan_merit", "merit": float("nan"), "grounded": True},
        {"id": "finite_grounded", "merit": 0.25, "grounded": True},
    ]
    out = felt_judgment(opts, FeltState(hormones=dict(_NEUTRAL)))
    ranked = {row["id"]: row for row in out["ranked"]}

    assert ranked["truthy_string"]["eligible"] is False
    assert ranked["nan_merit"]["eligible"] is False
    assert ranked["nan_merit"]["felt_score"] == 0.0
    assert out["chosen"] == "finite_grounded"


def test_nonfinite_felt_telemetry_is_ignored_and_output_stays_finite():
    """Digital hormones may allocate attention, but corrupt values may never choose or emit NaN."""
    felt = FeltState(
        hormones={**_NEUTRAL, "cortisol": float("nan"), "dopamine": float("inf")},
        vitals={"knowledge": float("-inf")},
        markers={"shiny": float("nan")},
    )
    opts = [
        {"id": "higher_merit", "merit": 0.6, "risk": 1.0, "novelty": 1.0,
         "concepts": ["shiny"], "relieves": "knowledge"},
        {"id": "lower_merit", "merit": 0.5},
    ]
    out = felt_judgment(opts, felt)

    assert out["chosen"] == "higher_merit"
    assert out["felt_trace"] == []
    assert all(math.isfinite(row["felt_score"]) for row in out["ranked"])


def test_moral_core_tamper_refuses_to_judge(monkeypatch):
    """If the moral spine itself has drifted, the felt organ refuses to make ANY preference-driven
    choice — a compromised morality is not a body one is allowed to choose from."""
    monkeypatch.setattr(fj, "_moral_core_intact", lambda: False)
    out = felt_judgment(_options(), FeltState(hormones=dict(_NEUTRAL)))
    assert out["chosen"] is None
    assert "moral core" in out["note"].lower()


def test_moral_integrity_check_failure_refuses_to_judge(monkeypatch):
    """Import/runtime failure of the integrity check is uncertainty, never permission."""
    from packages.graph_scale import moral_invariants

    def _broken_integrity():
        raise RuntimeError("injected integrity failure")

    monkeypatch.setattr(moral_invariants, "verify_integrity", _broken_integrity)
    out = felt_judgment(_options(), FeltState(hormones=dict(_NEUTRAL)))
    assert out["chosen"] is None
    assert "integrity check failed" in out["note"].lower()


def test_non_boolean_moral_integrity_cannot_authorize(monkeypatch):
    """A malformed truthy value must not cross the immutable integrity boundary."""
    from packages.graph_scale import moral_invariants

    monkeypatch.setattr(
        moral_invariants,
        "verify_integrity",
        lambda: {"ok": "false"},
    )
    out = felt_judgment(_options(), FeltState(hormones=dict(_NEUTRAL)))
    assert out["chosen"] is None
    assert "integrity check failed" in out["note"].lower()


def test_moral_option_screen_failure_blocks_every_option(monkeypatch):
    """Once core integrity is known, a broken per-option screen still fails closed."""
    from packages.graph_scale import moral_invariants

    def _broken_evaluate(_text):
        raise ValueError("injected option-screen failure")

    monkeypatch.setattr(moral_invariants, "evaluate", _broken_evaluate)
    out = felt_judgment(_options(), FeltState(hormones=dict(_NEUTRAL)))
    assert out["chosen"] is None
    assert out["ranked"]
    assert all(row["eligible"] is False for row in out["ranked"])
    assert all("moral 0th gate unavailable" in row["blocked_reason"] for row in out["ranked"])


# ── the organ is actually wired to the LIVE body (integration smoke, not a fixture) ──────────────

def test_reads_live_felt_state_without_crashing():
    """felt_judgment with no context reads the REAL live body (self_state.json hormones + stakes
    vitals). It must run and return a coherent verdict against whatever the live state is."""
    out = felt_judgment(_options())            # no context → live read
    assert out["felt_state_source"] in ("live", "neutral")
    assert out["chosen"] in {"study_physics", "call_a_friend", "rest_quietly"} or out["chosen"] is None
    assert isinstance(out["felt_trace"], list)
    assert "agent_relative" in out and "no_felt_basis" in out


def test_demo_two_felt_states_flips():
    """The runnable headline demo returns a genuine flip with traces on both sides."""
    d = fj.demo_two_felt_states()
    assert d["flipped"] is True
    assert d["state_a_choice"] != d["state_b_choice"]
    assert d["state_a_trace"] and d["state_b_trace"]
