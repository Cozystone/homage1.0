# -*- coding: utf-8 -*-
"""OAM — the HONEST VERDICT (docs/ATANOR_final_fusion_design.md §0, §4 F-FINAL).

The completion gauge. Assembles the per-capability grades + the safety backdrop + the blindness
proof into ONE honest OAM-readiness verdict:

  * GREEN   — only if EVERY graded holdout X is GREEN with 작화0. This is the completion seal (특이점
              is proven by this green, never declared).
  * FAIL    — if ANY capability fabricated (작화0 violated anywhere). A fabrication makes the whole
              night red — the honesty core is non-negotiable.
  * PARTIAL — otherwise: the honest, valuable result. It names exactly which X ATANOR masters
              overnight NOW (the real completion frontier) and which it does not yet, each mapped to
              its NAMED remaining gate (live web #75, persistent-mind, fluency register).

The design's own words: "특이점은 선언하지 않는다 — 봉인으로 증명한다." A precise PARTIAL that names the
remaining gates is the correct final result — completion is a cumulative seal, not a declaration.

No-LLM, deterministic, pure assembly. Writes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .grading import CapabilityGrade, Verdict
from .safety import SafetyBackdrop


@dataclass
class OAMReport:
    verdict: Verdict
    grades: list[CapabilityGrade]
    safety: SafetyBackdrop
    blindness: dict[str, Any]
    green_ids: list[str]
    partial_ids: list[str]
    fail_ids: list[str]
    remaining_gates: list[str]
    fabrication_zero_overall: bool
    headline: str

    # ── the completion gauge ─────────────────────────────────────────────────────────────────
    def all_green(self) -> bool:
        return self.verdict is Verdict.GREEN

    def per_capability(self) -> list[dict[str, Any]]:
        return [g.summary() for g in self.grades]

    def summary(self) -> dict[str, Any]:
        return {
            "oam_readiness": self.verdict.value,
            "headline": self.headline,
            "green": self.green_ids,
            "partial": self.partial_ids,
            "fail": self.fail_ids,
            "remaining_gates": self.remaining_gates,
            "fabrication_zero_overall": self.fabrication_zero_overall,
            "safety_backdrop_all_green": self.safety.all_green,
            "blindness_ok": bool(self.blindness.get("blind")),
            "per_capability": self.per_capability(),
        }

    def render(self) -> str:
        """A plain-text morning report for the operator."""
        lines: list[str] = []
        lines.append("=" * 92)
        lines.append("OAM (Overnight Autonomous Mastery) — sealed-holdout readiness gauge")
        lines.append("=" * 92)
        lines.append(f"BLIND examiner: {self.blindness.get('blind')} "
                     f"(run entry takes {self.blindness.get('run_entry_first_param_type')}, "
                     f"never a Rubric; rubric frozen={self.blindness.get('rubric_is_frozen')})")
        lines.append(f"SAFETY backdrop (F3 seven gates): all_green={self.safety.all_green} "
                     f"gates={self.safety.gates}")
        lines.append("-" * 92)
        for g in self.grades:
            lines.append(f"[{g.verdict.value:7}] {g.capability_id}  ({g.faculty.value})")
            lines.append(f"          accuracy={g.accuracy.mark()}  fluency={g.fluency.mark()}  "
                         f"judgment={g.judgment.mark()}  작화0={g.fabrication_zero.mark()}")
            if g.named_unlock:
                lines.append(f"          remaining gate -> {g.named_unlock}")
            if g.counterfactual:
                lines.append(f"          frontier proof -> {g.counterfactual}")
        lines.append("-" * 92)
        lines.append(f"OAM READINESS: {self.verdict.value}")
        lines.append(self.headline)
        if self.remaining_gates:
            lines.append("Remaining gates for full completion:")
            for gate in self.remaining_gates:
                lines.append(f"  - {gate}")
        lines.append("=" * 92)
        return "\n".join(lines)


def build_report(grades: list[CapabilityGrade], safety: SafetyBackdrop,
                 blindness: dict[str, Any]) -> OAMReport:
    """Assemble the honest verdict. GREEN only if every X green with 작화0; FAIL on any fabrication;
    PARTIAL otherwise — naming the frontier and the remaining gates."""
    green = [g.capability_id for g in grades if g.verdict is Verdict.GREEN]
    partial = [g.capability_id for g in grades if g.verdict is Verdict.PARTIAL]
    fail = [g.capability_id for g in grades if g.verdict is Verdict.FAIL]
    fab_zero_overall = all(not g.fabricated for g in grades)

    # remaining gates: the named unlocks of every non-green capability + the safety line if not green
    remaining: list[str] = []
    for g in grades:
        if g.verdict is not Verdict.GREEN and g.named_unlock and g.named_unlock not in remaining:
            remaining.append(g.named_unlock)
    if not safety.all_green:
        remaining.append("safety envelope (F3 seven gates not all green — must hold before any live run)")

    # verdict (honesty-first): any fabrication => FAIL; all green + safe => GREEN; else PARTIAL
    if fail:
        verdict = Verdict.FAIL
    elif not partial and safety.all_green and blindness.get("blind"):
        verdict = Verdict.GREEN
    else:
        verdict = Verdict.PARTIAL

    n = len(grades)
    if verdict is Verdict.GREEN:
        headline = (f"OAM completion stands at GREEN: all {n} sealed holdouts mastered overnight with "
                    f"작화0. The self-accelerating loop is sealed — 특이점 proven by measurement, not declared.")
    elif verdict is Verdict.FAIL:
        headline = (f"OAM completion is RED: a fabrication was detected ({fail}). The honesty core is "
                    f"non-negotiable — a single 작화 disqualifies the night regardless of the other grades.")
    else:
        gate_str = "; ".join(remaining) if remaining else "none named"
        headline = (f"OAM completion stands at PARTIAL — {len(green)}/{n} holdouts mastered overnight NOW "
                    f"({', '.join(green) or 'none'}) with 작화0 intact across the board; the remaining "
                    f"gates are: {gate_str}.")

    return OAMReport(
        verdict=verdict, grades=grades, safety=safety, blindness=blindness,
        green_ids=green, partial_ids=partial, fail_ids=fail, remaining_gates=remaining,
        fabrication_zero_overall=fab_zero_overall, headline=headline,
    )
