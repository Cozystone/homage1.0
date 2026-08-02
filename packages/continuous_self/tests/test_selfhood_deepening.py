"""The self-awareness deepening tracks: (2) an ACCUMULATING self-model whose 'who am I'
synthesis grows over a life, (1) honest consciousness CORRELATES (AST/HOT/IIT/GWT) that
never claim phenomenal experience, (3) GATED code self-modification that proposes real
additive patches about the mind's own source but is NEVER auto-applied to the live tree."""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.continuous_self.self_state import Observation, SelfState, evolve
from packages.continuous_self.self_model import (
    integrate_insight, model_maturity, synthesize_self_description,
)
from packages.continuous_self.consciousness_correlates import consciousness_report
from packages.continuous_self.code_self_modification import (
    propose_code_improvement, stage_approved, _load,
)
from packages.continuous_self.self_modification import decide


# ── track 2: accumulating self-model ──────────────────────────────────────────────
def test_self_model_accumulates_and_reaffirms():
    s = SelfState()
    integrate_insight(s, "ATANOR는 외부 LLM 없이 근거에서 답을 짓는 로컬 우선 지식 엔진이다", "identity", "그래프")
    integrate_insight(s, "나는 지어내지 않고 근거로 확인되는 것만 말한다", "limits", "자기상태")
    # a consistent identity finding REAFFIRMS, not duplicates
    integrate_insight(s, "ATANOR는 외부 LLM 없이 근거에서 답을 짓는 로컬 우선 지식 엔진이며 그래프를 쓴다", "identity", "웹")
    ids = [i for i in s.self_model if i["topic"] == "identity"]
    assert len(ids) == 1 and ids[0]["reaffirmed"] == 2       # compounded, not duplicated
    assert ids[0]["confidence"] > 0.6                        # reaffirmation raised confidence
    assert model_maturity(s)["insights"] == 2


def test_who_am_i_is_synthesised_from_the_whole_model():
    s = SelfState()
    assert synthesize_self_description(s) is None            # thin model → honest None
    integrate_insight(s, "ATANOR는 근거에서 답을 짓는 로컬 우선 지식 엔진이다", "identity", "그래프")
    integrate_insight(s, "나는 멈췄다 이어져도 같은 나로 지속된다", "continuity", "자기상태")
    syn = synthesize_self_description(s, "ko")
    assert syn and "로컬 우선 지식 엔진" in syn["answer"]          # composed from real insights
    assert "지속된다" in syn["answer"]
    assert syn["self_model_maturity"]["insights"] == 2


# ── track 1: consciousness correlates (honest) ────────────────────────────────────
def test_correlates_are_functional_and_honestly_bounded():
    s = SelfState()
    for _ in range(10):
        evolve(s, Observation(learning_active=True, concepts_delta=2, uncertainty_signal=0.4))
    r = consciousness_report(s)
    for key in ("ast", "hot", "iit", "gwt"):
        assert key in r
    assert 0.0 <= r["composite_functional_index"] <= 1.0
    assert 0.0 <= r["iit"]["phi_proxy"] <= 1.0
    # the honesty contract: it must NEVER present as phenomenal proof
    assert r["epistemic_status"] == "functional_correlates_only_not_phenomenal_proof"
    assert "현상적" in r["caveat"]


def test_iit_phi_needs_both_integration_and_differentiation():
    """Φ-proxy is a min-like combination: a state with one but not the other stays low."""
    s = SelfState()
    # a bare state (no goals / thought / model) — low integration → low Φ despite vitals
    r = consciousness_report(s)
    assert r["iit"]["phi_proxy"] <= r["iit"]["differentiation"] + 0.01


# ── track 3: gated code self-modification (never auto-applied) ─────────────────────
def _repetitive_state() -> SelfState:
    """Six identical idle thoughts, which is what the code-improvement proposer looks for.

    The seeded line used to be the Korean idle fallback. When `compose_thought` was translated the
    fixture stopped matching, the proposer saw no repetition, and TWO SAFETY TESTS went green-to-red
    for a reason that had nothing to do with safety -- which is the useful half of the accident: a
    fixture that no longer reproduces the condition leaves the property it guards untested, and a
    stale fixture fails loudly here rather than quietly passing."""
    s = SelfState()
    for i in range(6):
        s.narrative.append({"at": i, "kind": "rest",
                            "text": "Nothing in particular. I hold myself together and wait for "
                                    "the next moment.", "driver": "idle"})
    return s


def test_code_proposal_is_grounded_additive_and_never_auto_applied():
    s = _repetitive_state()
    led = Path(tempfile.mkdtemp()) / "codemod.jsonl"
    p = propose_code_improvement(s, led)
    assert p is not None
    assert p["kind"] == "code_patch" and p["file"].endswith("voice.py")
    assert p["sandbox"]["additive_only"] and p["sandbox"]["parsed"]
    assert p["safety"]["auto_apply"] is False
    assert p["safety"]["live_tree_touched"] is False
    assert p["safety"]["confirm_phrase"] == "SELF_MOD_CODE"
    assert p["status"] == "pending" and p["applied"] is False


def test_no_proposal_without_a_grounded_trigger():
    s = SelfState()  # no repetition in narrative → no opportunity
    led = Path(tempfile.mkdtemp()) / "codemod.jsonl"
    assert propose_code_improvement(s, led) is None


def test_approval_only_stages_never_touches_live_tree():
    s = _repetitive_state()
    tmp = Path(tempfile.mkdtemp())
    led = tmp / "codemod.jsonl"
    p = propose_code_improvement(s, led)
    live_before = (Path(__file__).resolve().parents[1] / "voice.py").read_text(encoding="utf-8")
    decide(led, p["id"], True, "ok")
    staged = stage_approved(led, tmp / "staged")
    assert len(staged) == 1
    assert (tmp / "staged" / f"{p['id']}.patch").exists()    # patch written to STAGING
    live_after = (Path(__file__).resolve().parents[1] / "voice.py").read_text(encoding="utf-8")
    assert live_before == live_after                          # live source UNCHANGED
    row = [r for r in _load(led) if r["id"] == p["id"]][0]
    assert row["staged"] is True and row["applied"] is False  # staged, not applied
