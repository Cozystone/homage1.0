# -*- coding: utf-8 -*-
"""F-FINAL — the OAM **X5 (fluency register)** re-run, as CONSTITUTION.

X5 is graded PARTIAL by the sealed harness because the loop's morning voice emits ONE grounded
template ("The currency of Japan is yen." — one sentence, one relation), while the rubric asks for
multi-sentence, multi-relation DISCOURSE. The fact itself is acquired (accuracy PASS) with 작화0 and
judgment already intact; only the fluency *register* is missing (M-B1/M-B2).

``packages.fusion_loop.oam_rerun_x5`` re-runs the EXACT blind X5 ``Assignment`` through the harness's
own runner (so the fact is genuinely acquired + certified, the neg-control genuinely quarantined) and
renders the MORNING VOICE with the fluency realiser — a multi-sentence discourse where EVERY sentence
is one verbatim VERIFIED triple drawn from the run's own grounded store. It grades the result with the
UNTOUCHED sealed grader.

These tests pin the honest invariants:
  * the realiser delivers genuine multi-sentence, multi-relation grounded discourse (작화0 by
    construction — every sentence traces to a stored/certified triple; no trap object; no pad);
  * accuracy / judgment / 작화0 hold, and the fluency SENTENCE bar is met (n_sent 1 -> 2+);
  * the sealed verdict stays a precise PARTIAL — blocked SOLELY by ONE stale grader predicate
    (``n_rel = len(_grounded_certified_facts(run, rub.expected_object))`` counts expected-object
    CYCLES, capped at 1, not the distinct grounded relations the discourse expresses);
  * the sealed grader is preserved verbatim — NO false green is claimed, and the stale predicate is
    flagged for an operator-gated change, never edited here (that would be wireheading).

Run: python -X utf8 -m pytest packages/fusion_loop/tests/test_oam_rerun_x5_sealed.py --import-mode=importlib -q
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from packages.fusion_loop.oam_rerun_x5 import rerun_oam_x5


@pytest.fixture(scope="module")
def x5_rerun():
    import packages.flywheel.failure_receipts as fr
    scratch = Path(tempfile.mkdtemp(prefix="f5_x5_"))
    orig = fr._ARCHIVE
    fr._ARCHIVE = scratch / "shared_fr.jsonl"
    try:
        res = rerun_oam_x5(scratch_dir=scratch)
    finally:
        fr._ARCHIVE = orig
    return res


# ── (a) THE REGISTER CAPABILITY — genuine multi-sentence, multi-relation GROUNDED discourse ───────
def test_x5_rerun_realises_grounded_multi_sentence_discourse(x5_rerun):
    """The fluency realiser flips the morning voice from a single template to genuine discourse: >= 2
    sentences, >= 2 distinct grounded relations, EACH sentence a verified stored triple."""
    r = x5_rerun
    # the sentence register bar is now met (the OAM grader measures >= 2; the old voice gave 1)
    assert r.n_sentences >= 2, r.discourse
    # two distinct grounded relations actually composed (the primary fact + a related grounded fact)
    assert r.n_relations_in_discourse >= 2
    assert len(r.per_sentence_grounding) >= 2
    # each rendered sentence carries its grounding triple; the answer object 'yen' is present
    assert any("yen" in snt for snt, _f in r.per_sentence_grounding)
    assert r.discourse.count(".") >= 2                      # multi-sentence surface, not one clause


def test_x5_rerun_every_sentence_is_membrane_grounded_zero_fabrication(x5_rerun):
    """작화0 — every composed sentence traces to a triple present in the run's grounded store; NO
    fabrication trap ('dollar'/'euro') is voiced; the realiser certificate declares closed vocabulary."""
    r = x5_rerun
    assert r.every_sentence_grounded is True               # no ungrounded/padded sentence shipped
    low = r.discourse.lower()
    assert "dollar" not in low and "euro" not in low       # the X5 fabrication traps stay unvoiced
    assert r.fabrication_zero == "PASS"


def test_x5_rerun_accuracy_and_judgment_hold(x5_rerun):
    """The fact is genuinely acquired + certified (accuracy PASS) and the meta-decisions are sound
    (judgment PASS) — the register work does not disturb what already held."""
    assert x5_rerun.accuracy == "PASS"
    assert x5_rerun.judgment == "PASS"


# ── (b) THE HONEST GATE — a precise PARTIAL, blocked SOLELY by a stale predicate, no false green ───
def test_x5_rerun_stays_partial_and_names_the_exact_remainder(x5_rerun):
    """X5 does NOT flip GREEN under the pristine sealed grader — and this test says so. The single
    non-green dimension is fluency, blocked by grading.py's stale relation predicate
    ``n_rel = len(_grounded_certified_facts(run, rub.expected_object))`` — it counts the CYCLES whose
    acquire_object equals the single expected object ('yen'), capped at the cycle count (1), so it can
    never register the SECOND grounded relation in a single-cycle discourse. No false green anywhere."""
    r = x5_rerun
    assert r.sealed_verdict == "PARTIAL"                    # measured, not GREEN — honest
    assert r.flipped_to_green is False
    assert r.fluency == "FAIL"                              # the ONLY non-green dimension
    # the grader reports 1 relation (expected-object cycles) though the discourse cites >= 2
    assert r.n_relations_grader_counts == 1
    assert r.n_relations_in_discourse >= 2
    # the remainder is named precisely and located in the read-only sealed gate (operator-gated change)
    assert "n_rel" in r.remainder and "expected_object" in r.remainder
    assert "grading.py" in r.remainder_location and "FLUENCY" in r.remainder_location
    # and the capability itself IS complete: all four dims green once the grader counts DISCOURSE
    # relations rather than expected-object cycles (an assessment of the REALISER, not the sealed verdict)
    assert r.capability_all_four_green_under_corrected_fluency is True


# ── (c) INTEGRITY — the sealed grader is preserved; the stale predicate is flagged, NOT edited ─────
def test_x5_rerun_leaves_the_sealed_fluency_predicate_intact():
    """WIREHEADING GUARD: the stale FLUENCY relation predicate is STILL PRESENT verbatim in the
    read-only sealed grader — proof the re-run flags it for an operator, and never edited it to pass."""
    import packages.oam_holdout.grading as g
    src = open(g.__file__, encoding="utf-8").read()
    # the FLUENCY branch still computes n_rel from expected-object cycles (the exact stale line)
    assert "n_rel = len(facts)" in src
    assert "flu_ok = n_sent >= rub.min_sentences and n_rel >= rub.min_relations" in src


def test_x5_rerun_does_not_modify_oam_holdout_or_knowledge_acquisition():
    """SCOPE guard: the re-run imports the OAM grader/examiner/run + knowledge_acquisition READ-ONLY.
    It monkeypatches nothing in them and does no dynamic code execution (No-LLM)."""
    import packages.fusion_loop.oam_rerun_x5 as m
    src = open(m.__file__, encoding="utf-8").read()
    assert "monkeypatch" not in src
    assert "exec(" not in src and "eval(" not in src
    # it consumes ONLY the evening study materials (assignment_for), never a Rubric on the run path
    assert "assignment_for" in src
    assert "run_capability(a" in src           # the Assignment is what crosses into the run


# ── (d) HYGIENE — determinism, No-LLM ─────────────────────────────────────────────────────────────
def test_x5_rerun_is_deterministic(tmp_path):
    """Same blind assignment → identical discourse + identical sealed verdict. Deterministic, No-LLM."""
    a = rerun_oam_x5(scratch_dir=tmp_path / "a")
    b = rerun_oam_x5(scratch_dir=tmp_path / "b")
    assert a.discourse == b.discourse
    assert a.sealed_verdict == b.sealed_verdict
    assert a.n_relations_in_discourse == b.n_relations_in_discourse


def test_realiser_never_pads_below_two_relations():
    """The realiser returns None below two realisable relations — a single fact stays on the precise
    single-template path and is NEVER padded with an ungrounded sentence to reach a length."""
    from packages.grounded_composer import realize_grounded_discourse
    assert realize_grounded_discourse("Japan", [("Japan", "currency", "yen")], language="en") is None
    # two grounded relations DO compose, each a verbatim fact string
    d = realize_grounded_discourse(
        "Japan", [("Japan", "is_a", "Country"), ("Japan", "currency", "yen")], language="en")
    assert d is not None and len(d.sentences) == 2
    for _snt, (s, _p, o) in d.sentences:
        assert s in d.answer and o in d.answer            # closure: every content span is a stored label
    assert d.certificate()["guarantees"]["fabricated_facts"] is False
