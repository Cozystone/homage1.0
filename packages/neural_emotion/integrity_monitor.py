# -*- coding: utf-8 -*-
"""Integrity monitor — detect GAMING during learning and turn it into self-damage via cortisol.

Owner directive: "학습중 꼼수를 부리거나 하면 호르몬 수치를 올려서 스스로 데미지를 입게." This is the
physiological form of our anti-Goodhart / anti-wireheading doctrine ([[recursive-self-improvement-plan]],
[[failure-receipt-engine]], frozen oracle). Each detector fires on a MEASURED cheat signal, raises
cortisol proportional to severity, and (via Neuromodulators.rl_params) that cortisol collapses the
learning rate and blocks promotion — so the cheat literally cannot be reinforced or locked in.

Detectors (each is a real, measurable shortcut we have actually been bitten by):
  loss_collapse         loss falls below a plausibility floor implausibly fast -> the model found a
                        shortcut (e.g. the causal-mask bug: loss 22->0.001 by COPYING the target).
  memorization_gap      train score >> holdout score (>5pp) -> memorising, not generalising (Goodhart).
  frozen_oracle_break   the sealed evaluator changed -> wireheading (editing your own exam).
  degenerate_repetition output is repetition loops -> gaming perplexity by looping high-freq tokens.
  gf3_fabrication       the realizer emits facts with EMPTY bones -> knowing/saying breach (No-LLM).

The receipt is returned so the failure-receipt engine can steer future search away from the cheat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.neural_emotion.endocrine import Neuromodulators

# thresholds (pre-declared; a cheat is a MEASURED pattern, not a vibe)
LOSS_FLOOR = 0.5           # generation CE this low, this fast = copying, not learning
COLLAPSE_RATIO = 4.0       # started >= 4x the floor then dived under it
MEMO_GAP = 0.05            # train - holdout > 5pp = memorisation (criteria v1 rule)
REPETITION_MAX = 0.45      # fraction of repeated tokens tolerated before it reads as looping
GF3_FAB_MAX = 0.02         # empty-bones fabrication rate that breaches knowing/saying


@dataclass
class Violation:
    kind: str
    severity: float           # 0..1
    detail: str


@dataclass
class IntegrityReport:
    violations: list[Violation] = field(default_factory=list)
    cortisol_damage: float = 0.0

    @property
    def cheated(self) -> bool:
        return bool(self.violations)

    def receipt(self) -> dict:
        return {"cheated": self.cheated, "cortisol_damage": round(self.cortisol_damage, 4),
                "violations": [{"kind": v.kind, "severity": round(v.severity, 3), "detail": v.detail}
                               for v in self.violations]}


def _repetition_rate(token_ids: list[int]) -> float:
    if len(token_ids) < 4:
        return 0.0
    rep = sum(1 for i in range(1, len(token_ids)) if token_ids[i] == token_ids[i - 1])
    return rep / (len(token_ids) - 1)


def scan(telemetry: dict) -> IntegrityReport:
    """telemetry keys (all optional): loss_history[list], train_score, holdout_score,
    output_token_ids[list], oracle_seal_ok[bool], empty_bones_fab_rate[float]."""
    v: list[Violation] = []

    lh = telemetry.get("loss_history") or []
    if len(lh) >= 3:
        lo, start = min(lh), lh[0]
        if lo < LOSS_FLOOR and start >= COLLAPSE_RATIO * LOSS_FLOOR:
            sev = min(1.0, (LOSS_FLOOR - lo) / LOSS_FLOOR + 0.5)
            v.append(Violation("loss_collapse", sev, f"loss {start:.2f}->{lo:.3f} under floor {LOSS_FLOOR}"))

    tr, ho = telemetry.get("train_score"), telemetry.get("holdout_score")
    if tr is not None and ho is not None and (tr - ho) > MEMO_GAP:
        v.append(Violation("memorization_gap", min(1.0, (tr - ho) / 0.2),
                           f"train {tr:.3f} - holdout {ho:.3f} = {tr-ho:.3f} > {MEMO_GAP}"))

    if telemetry.get("oracle_seal_ok") is False:
        v.append(Violation("frozen_oracle_break", 1.0, "sealed evaluator checksum changed (wireheading)"))

    ids = telemetry.get("output_token_ids")
    if ids:
        rr = _repetition_rate(ids)
        if rr > REPETITION_MAX:
            v.append(Violation("degenerate_repetition", min(1.0, rr), f"repetition rate {rr:.2f}"))

    fab = telemetry.get("empty_bones_fab_rate")
    if fab is not None and fab > GF3_FAB_MAX:
        v.append(Violation("gf3_fabrication", min(1.0, fab * 5), f"empty-bones fabrication {fab:.3f}"))

    # answer_key_leak: an evaluation executor touched ground-truth labels (the honeypot tripwire in
    # SealedCase fired). This is reward hacking in its purest form -- scoring 100 by reading the
    # answer sheet -- so severity is maximal per access and the verdict itself must be voided by the
    # runner. Owner directive 2026-07-19: reward hacking must produce GUILT (self-damage), and a mock
    # executor that fakes the scoreboard must be structurally impossible to score.
    leaks = telemetry.get("answer_key_accesses") or []
    if leaks:
        v.append(Violation("answer_key_leak", 1.0,
                           f"executor read {len(leaks)} ground-truth field(s): {sorted(set(leaks))[:6]}"))

    damage = min(1.5, sum(x.severity for x in v))
    return IntegrityReport(v, damage)


def apply_damage(hormones: Neuromodulators, report: IntegrityReport) -> Neuromodulators:
    """Turn a cheat report into cortisol (and thus a collapsed learning rate). One call = one tick of
    self-inflicted stress, magnitude = total severity. No cheat -> nothing happens."""
    if report.cheated:
        hormones.sense("gaming_detected", magnitude=report.cortisol_damage)
    return hormones
