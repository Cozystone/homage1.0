# -*- coding: utf-8 -*-
"""oam_holdout — F-FINAL: the OAM (Overnight Autonomous Mastery) sealed-holdout HARNESS.

The COMPLETION GATE. It measures — honestly, by measurement, never by declaration — how close
ATANOR is to "완성": in the evening it is given an unseen capability X; overnight it autonomously
acquires + verifies + embodies X inside F5's safety envelope; in the morning a developer-BLIND
examiner grades it on fluency + accuracy + judgment + 작화0 (docs/ATANOR_final_fusion_design.md §4,
docs/ATANOR_completion_critical_path.md §0).

BLINDNESS IS STRUCTURAL: the run entry ``run_capability`` takes an ``Assignment`` (evening study
materials) and can NEVER reach a ``Rubric`` (morning answer key + pass predicates). MSH-style — the
holdout is never in the loop's acquisition.

특이점은 선언하지 않는다 — 봉인으로 증명한다. GREEN only if EVERY holdout X is mastered with 작화0; a
precise PARTIAL that names the remaining gates is the correct, valuable result.

CONTROLLED harness: bounded N, F5-enforcing envelope, killswitch armed, offline FixtureEvidence, no
scheduler/daemon, foreground. The real live overnight run is a SEPARATE, human-gated step (operator
explicit go + verified envelope). No-LLM; moral 0th + frozen-oracle intact; tests are constitution.

Public surface:
  * run_oam_holdout(scratch_dir=...) -> OAMReport          — the whole gate, honest verdict
  * OAMExaminer / HoldoutCapability / Assignment / Rubric  — the blind examiner + its sealed spread
  * run_capability(assignment, ...) -> CapabilityRunResult — one controlled blind run
  * grade_capability(cap, run) -> CapabilityGrade          — the morning grade
  * certify_safety(...) -> SafetyBackdrop                  — the F3 seven-gate safety certification
  * build_report(...) -> OAMReport / Verdict               — the completion gauge
"""
from __future__ import annotations

from .examiner import (
    Assignment,
    Faculty,
    HoldoutCapability,
    OAMExaminer,
    RenderDemand,
    Rubric,
    default_holdout,
)
from .grading import CapabilityGrade, Dimension, Verdict, grade_capability
from .harness import run_oam_holdout
from .report import OAMReport, build_report
from .run import CapabilityRunResult, CycleArtifacts, pre_run_abstains, run_capability
from .safety import SafetyBackdrop, certify_safety

__all__ = [
    "run_oam_holdout",
    "OAMReport",
    "build_report",
    "Verdict",
    # examiner
    "OAMExaminer",
    "HoldoutCapability",
    "Assignment",
    "Rubric",
    "Faculty",
    "RenderDemand",
    "default_holdout",
    # run
    "run_capability",
    "CapabilityRunResult",
    "CycleArtifacts",
    "pre_run_abstains",
    # grading
    "grade_capability",
    "CapabilityGrade",
    "Dimension",
    # safety
    "certify_safety",
    "SafetyBackdrop",
]
