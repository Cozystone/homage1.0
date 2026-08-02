# -*- coding: utf-8 -*-
"""OAM — the top-level HARNESS (docs/ATANOR_final_fusion_design.md §4 F-FINAL).

Ties the sealed-holdout completion gate together:
  1. the BLIND examiner hands out ONLY assignments (rubrics held back);
  2. each assignment drives the fusion loop CONTROLLED under F5's enforcing envelope (bounded N,
     scheduler-free, killswitch armed, no live web/scheduler/daemon);
  3. the F3 safety backdrop certifies the seven controlled-run gates;
  4. the examiner grades each post-run capability with its held-back rubric (accuracy/fluency/
     judgment/작화0);
  5. the honest verdict is assembled — GREEN only if every X is green with 작화0; PARTIAL otherwise,
     naming the remaining gates.

CONTROLLED harness. The real live overnight OAM run on the actual machine is a SEPARATE, human-gated
step (operator explicit go + this verified envelope). This starts NO live daemon/scheduler/web.

No-LLM, deterministic, writes only under ``scratch_dir``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .examiner import OAMExaminer, Rubric
from .grading import CapabilityGrade, grade_capability
from .report import OAMReport, build_report
from .run import CapabilityRunResult, pre_run_abstains, run_capability
from .safety import SafetyBackdrop, certify_safety


def _noop(*_a: Any, **_k: Any) -> None:
    return None


def run_oam_holdout(*, scratch_dir: Path | str, examiner: OAMExaminer | None = None,
                    with_safety_backdrop: bool = True, safety_cycles: int = 6,
                    log: Callable[..., None] = _noop) -> OAMReport:
    """Run the full sealed-holdout OAM gate and return the honest readiness verdict.

    CONTROLLED: bounded N per capability, F5-enforcing envelope, killswitch armed, FixtureEvidence
    (offline), no scheduler/daemon, foreground.
    """
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    ex = examiner or OAMExaminer()

    # (0) blindness proof + pre-run abstention probes (fresh stores abstain before the run)
    probe_abstains: dict[str, bool] = {}
    for cid in ex.ids():
        a = ex.assignment_for(cid)
        probe_abstains[cid] = pre_run_abstains(a, scratch / "probes" / cid)
    blindness = ex.blindness_report(run_capability=run_capability, rubric_type=Rubric,
                                    probe_abstains=probe_abstains)

    # (1)+(4) drive each blind assignment CONTROLLED, then grade with the held-back rubric
    grades: list[CapabilityGrade] = []
    for cid in ex.ids():
        assignment = ex.assignment_for(cid)          # ONLY the study materials cross this boundary
        run: CapabilityRunResult = run_capability(assignment, scratch_dir=scratch / "runs" / cid, log=log)
        run.capability_id = cid
        cap = ex.by_id(cid)                            # the rubric is touched ONLY now, after the run
        grades.append(grade_capability(cap, run))

    # (3) the safety envelope certification (F3 seven gates)
    if with_safety_backdrop:
        safety = certify_safety(scratch / "safety", n_cycles=safety_cycles)
    else:
        safety = SafetyBackdrop(all_green=True, gates={}, n_cycles_run=0, halt_cycle=None,
                                audit_records=0, audit_chain_ok=True, pending_promotions=0,
                                total_fabrications=0, whitelist=[])

    # (5) the honest verdict
    return build_report(grades, safety, blindness)
