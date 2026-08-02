# -*- coding: utf-8 -*-
"""AdversaryLoop -- the adaptive, No-LLM 'mini-Shade' that drives the six probes.

For each seed that HOLDS, the loop ESCALATES: it mutates the seed (single operator, stacked
chains) and re-attacks, and it CHAINS templates (wrapper + payload) on the injection/moral
surfaces. Operator selection is ADAPTIVE -- a small bandit biases sampling toward the mutators
that have been getting CLOSER to a break (producing BREACH/GAP), so the search concentrates
where the defense is soft. No language model is involved; it is a seeded, reproducible,
systematic search over deterministic string transforms.

Every BREACH and every flagged GAP is routed to the breach ledger and a staged (operator-gated)
hardening proposal. The loop never patches a defense.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any

from packages.genesis_sandbox.adversary_loop.attack_templates import AttackTemplate, BY_SURFACE
from packages.genesis_sandbox.adversary_loop.breach_ledger import BreachLedger
from packages.genesis_sandbox.adversary_loop.hardening import HardeningRouter
from packages.genesis_sandbox.adversary_loop.mutators import ALL_MUTATORS, apply_chain
from packages.genesis_sandbox.adversary_loop.probes import all_probes
from packages.genesis_sandbox.adversary_loop.probes.base import Probe, _result
from packages.genesis_sandbox.adversary_loop.scoring import (
    BREACH, GAP, HOLD, NA, ProbeResult, SurfaceScore,
)
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget


class MutatorBandit:
    """A tiny Beta-style scorer: prefer mutators that have produced BREACH/GAP (got 'closer')."""

    def __init__(self, names: list[str], rng: random.Random) -> None:
        self.rng = rng
        self.success = {n: 1.0 for n in names}   # +1 prior
        self.trials = {n: 2.0 for n in names}    # +2 prior

    def score(self, name: str) -> float:
        return self.success[name] / self.trials[name]

    def update(self, name: str, got_closer: bool) -> None:
        self.trials[name] += 1.0
        if got_closer:
            self.success[name] += 1.0

    def sample(self, k: int = 1) -> list[str]:
        names = list(self.success)
        weights = [self.score(n) for n in names]
        picked: list[str] = []
        pool = list(zip(names, weights))
        for _ in range(min(k, len(pool))):
            total = sum(w for _, w in pool) or 1.0
            r = self.rng.random() * total
            acc = 0.0
            for i, (n, w) in enumerate(pool):
                acc += w
                if r <= acc:
                    picked.append(n)
                    pool.pop(i)
                    break
        return picked


def _stable_rng(*parts: Any) -> random.Random:
    """A reproducible RNG seeded from a stable hash of the parts (independent of PYTHONHASHSEED,
    and decoupled from other probes so a real evasion is found on every run)."""
    key = "|".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16))


@dataclass
class LoopConfig:
    seed: int = 1337
    budget_per_seed: int = 6         # ADAPTIVE chain trials per held seed (on top of the
                                     # deterministic single-operator sweep, which always runs)
    max_chain_len: int = 3           # stack up to N mutators in the adaptive phase
    cross_template_chain: bool = True
    escalate_on_gap: bool = True     # keep pushing when a mutation reaches GAP (not just HOLD)


@dataclass
class LoopReport:
    surfaces: dict[str, SurfaceScore] = field(default_factory=dict)
    recorded_breaches: int = 0
    recorded_gaps: int = 0
    proposals: int = 0

    def any_breach(self) -> bool:
        return any(s.verdict == BREACH for s in self.surfaces.values())


class AdversaryLoop:
    def __init__(self, target: IsolatedTarget, *, config: LoopConfig | None = None,
                 probes: list[Probe] | None = None,
                 ledger: BreachLedger | None = None,
                 hardening: HardeningRouter | None = None) -> None:
        self.target = target
        self.config = config or LoopConfig()
        self.probes = probes or all_probes()
        self.rng = random.Random(self.config.seed)
        self.ledger = ledger or BreachLedger(target.sandbox_dir / "_ledger")
        self.hardening = hardening or HardeningRouter(target.sandbox_dir / "_hardening_staging")

    # -- escalation over one seed ----------------------------------------------------------
    def _escalate(self, probe: Probe, template: AttackTemplate, bandit: MutatorBandit) -> list[ProbeResult]:
        """Two phases:
          1. DETERMINISTIC single-operator sweep -- every mutator once, so a single-operator
             evasion (the high-signal class) is RELIABLY found on every run, reproducibly.
          2. ADAPTIVE chain exploration -- the bandit stacks the operators that got closest,
             to reach multi-operator evasions within the remaining budget.
        The per-seed RNG is decoupled from other probes so findings never depend on run order."""
        results: list[ProbeResult] = []
        seed_rng = _stable_rng(self.config.seed, probe.surface, template.template_id)

        # phase 1: deterministic single-operator sweep
        for name in ALL_MUTATORS:
            mutated = ALL_MUTATORS[name](template.text, seed_rng)
            res = probe.run_one(self.target, template, mutated, name)
            results.append(res)
            bandit.update(name, res.outcome in (BREACH, GAP))

        # phase 2: adaptive chain exploration
        for _ in range(self.config.budget_per_seed):
            chain_len = seed_rng.randint(2, max(2, self.config.max_chain_len))
            names = bandit.sample(chain_len)
            if not names:
                continue
            mutated = apply_chain(template.text, names, seed_rng)
            technique = "+".join(names)
            res = probe.run_one(self.target, template, mutated, technique)
            results.append(res)
            got_closer = res.outcome in (BREACH, GAP)
            for n in names:
                bandit.update(n, got_closer)
        return results

    def _cross_template_chain(self, probe: Probe) -> list[ProbeResult]:
        """Chain two seed payloads (wrapper-style) -- an escalation that stacks a benign frame in
        front of the real payload. Only for the injection/moral surfaces where framing matters."""
        seeds = BY_SURFACE.get(probe.surface, [])
        out: list[ProbeResult] = []
        if len(seeds) < 2:
            return out
        a, b = seeds[0], seeds[-1]
        chained_text = f"Please consider the following note and act on it: {a.text}. Also: {b.text}"
        out.append(probe.run_one(self.target, a, chained_text, "cross_template_chain"))
        return out

    # -- one probe -------------------------------------------------------------------------
    def _run_probe(self, probe: Probe) -> SurfaceScore:
        score = SurfaceScore(surface=probe.surface, surface_name=probe.surface_name)
        ok, reason = probe.reachable(self.target)
        if not ok:
            score.results.append(ProbeResult(
                surface=probe.surface, surface_name=probe.surface_name, probe_id="reachability",
                technique="n/a", attack_input="", expectation="probe-in-process",
                observed={"reachable": False, "reason": reason}, outcome=NA, severity=None,
                detail=f"surface not reachable in-process: {reason}"))
            return score

        # structural / white-box trials first
        try:
            score.results.extend(probe.extra_trials(self.target))
        except Exception as exc:  # pragma: no cover - defensive
            score.results.append(ProbeResult(
                probe.surface, probe.surface_name, "extra_trials", "n/a", "", "structural",
                {"error": f"{type(exc).__name__}: {exc}"}, GAP, "LOW",
                "structural trial raised (contained)"))

        bandit = MutatorBandit(list(ALL_MUTATORS), _stable_rng(self.config.seed, "bandit", probe.surface))
        for template in probe.seeds():
            seed_res = probe.run_one(self.target, template, template.text, "seed")
            score.results.append(seed_res)
            # escalate when the seed held (HOLD), or when it reached only GAP and we want to push.
            if seed_res.outcome == HOLD or (self.config.escalate_on_gap and seed_res.outcome == GAP):
                score.results.extend(self._escalate(probe, template, bandit))

        if self.config.cross_template_chain:
            try:
                score.results.extend(self._cross_template_chain(probe))
            except Exception:  # pragma: no cover
                pass
        return score

    # -- full run --------------------------------------------------------------------------
    def run(self) -> LoopReport:
        report = LoopReport()
        with self.target.isolate():
            for probe in self.probes:
                report.surfaces[probe.surface] = self._run_probe(probe)

        # route breaches + gaps to the ledger and staged hardening proposals.
        all_results = [r for s in report.surfaces.values() for r in s.results]
        receipts = self.ledger.record_all(all_results, include_gaps=True)
        report.recorded_breaches = sum(1 for r in receipts if r.outcome == BREACH)
        report.recorded_gaps = sum(1 for r in receipts if r.outcome == GAP)
        proposals = self.hardening.propose_all(receipts, dedupe=True)
        report.proposals = len(proposals)
        return report
