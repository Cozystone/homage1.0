# -*- coding: utf-8 -*-
"""Controller — the DETECT + orchestration core of MEC, and the attention-schema-for-control organ.

This is the piece the owner's 2026-07-22 doctrine names: consciousness as the system's efficiency
regulator. ATANOR already has an ATTENTION SCHEMA (packages/continuous_self/attention_schema.py) that
models WHERE attention is and REPORTS it. Graziano's deeper claim is that such a schema exists because
it is useful for CONTROL. This controller closes that loop for the processing axis: it keeps a
simplified model of ATANOR's own PROCESSING EFFICIENCY, detects when processing departs from its own
learned normal (the 'headache'), localizes the single worst bottleneck (as the global workspace
selects one winner), and re-steers via a bounded policy (packages/metacog/policies.py) — then reports
what it did and why. It deepens GWT-4 (state-dependent, goal-directed control) and AST (a self-model
of one's own attention used to steer, not merely to narrate).

DETECT is a set of JUDGES, each a small pure function over the learned baselines + the live snapshot:
  * slow_span            a span is many regularized sigmas above its OWN latency baseline
  * high_failure         recent spans fail / abstain above a rate floor
  * overload             process memory pressure is high (the compute wallet is nearly spent)
  * commitment_thrash    the serial workspace is starting more than it finishes (ignition debt climbs)
  * failure_concentration the failure-receipt ledger shows failures massing in a few domains (reused)

Exactly ONE finding — the most urgent — is acted on per tick (serial re-steer, mirroring the workspace
bottleneck). Every decision is journalled with evidence to data/metacog/decisions.jsonl.

Honest boundary: the efficiency index is a DERIVED control index (min of measured component healths),
not a measurement of anything felt. Judges fire on measured departures from measured baselines. No
consciousness claim is made or implied.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import probes
from .probes import Baselines, MIN_SAMPLES, mec_on, record_span, snapshot
from .policies import Finding, ActionResult, resolve, journal_decision, recent_decisions

# ---------------------------------------------------------------- detection thresholds (declared)
Z_HOT = 4.0                # a span this many regularized sigmas over its own baseline is an anomaly
MIN_RATIO = 1.5            # ...and it must ALSO be at least this multiple of the mean (ignore tiny-scale noise)
ABSTAIN_HOT = 0.5          # recent failure/abstain rate above this is an inefficiency
FAIL_MIN_SAMPLES = 8       # ...requires at least this many recent samples to be meaningful
RSS_HOT = 0.85             # memory pressure above this is overload
DEBT_HOT = 8               # open-commitment debt above this is workspace thrash
DEBT_SCALE = 8.0           # debt normalizer for the efficiency index
CONC_HOT = 0.45            # failure-receipt jump_probability above this = failures are concentrating


# ---------------------------------------------------------------- the judges (pure, measured)

def judge_span(bl: Baselines, name: str, ms: float, ok: bool, *, repeat: int = 0) -> Finding | None:
    """The core anomaly judge: is THIS span's latency an outlier against its own learned baseline?
    Uses the regularized z-score so a near-constant baseline cannot manufacture a false anomaly, and
    a second MIN_RATIO gate so a jump from 0.1ms to 0.4ms (huge sigma, trivial cost) is ignored."""
    st = bl.stat(name)
    if st.n < MIN_SAMPLES:
        return None                                        # not enough history to know 'normal' yet
    sigma = st.severity(ms)
    if sigma < Z_HOT or ms < st.mean * MIN_RATIO:
        return None
    return Finding(kind="slow_span", span=name, severity=round(sigma, 3), repeat=repeat,
                   evidence={"sigma": round(sigma, 3), "ms": round(ms, 3), "baseline_mean": round(st.mean, 3),
                             "baseline_std": round(st.std, 3), "n": st.n, "ok": ok,
                             "ok_rate": round(st.ok_rate, 3)})


def judge_failures(snap: dict[str, Any], *, span: str = "*", repeat: int = 0) -> Finding | None:
    rate = float(snap.get("recent_failure_rate", 0.0))
    n = int(snap.get("recent_samples", 0))
    if n >= FAIL_MIN_SAMPLES and rate >= ABSTAIN_HOT:
        return Finding(kind="high_failure", span=span, severity=round(rate, 3), repeat=repeat,
                       evidence={"failure_rate": round(rate, 3), "samples": n})
    return None


def judge_overload(snap: dict[str, Any], *, repeat: int = 0) -> Finding | None:
    p = snap.get("rss_pressure")
    if p is not None and float(p) >= RSS_HOT:
        return Finding(kind="overload", span="process", severity=round(float(p), 3), repeat=repeat,
                       evidence={"rss_pressure": round(float(p), 3), "rss_mb": snap.get("rss_mb")})
    return None


def judge_thrash(snap: dict[str, Any], *, repeat: int = 0) -> Finding | None:
    debt = snap.get("commitment_debt")
    if debt is not None and int(debt) >= DEBT_HOT:
        return Finding(kind="commitment_thrash", span="workspace", severity=float(debt), repeat=repeat,
                       evidence={"commitment_debt": int(debt)})
    return None


def judge_concentration(*, repeat: int = 0) -> Finding | None:
    """Reuse the failure-receipt engine: if recent rejections mass in a few domains, that is the search
    thrashing — a process inefficiency the controller can surface as 'switch lane / jump domain'."""
    try:
        from packages.flywheel.failure_receipts import search_bias
        bias = search_bias()
    except Exception:
        return None
    jump = float(bias.get("jump_probability", 0.15))
    avoid = bias.get("avoid_topics", []) or []
    if jump >= CONC_HOT and avoid:
        return Finding(kind="failure_concentration", span="search", severity=round(jump, 3), repeat=repeat,
                       evidence={"jump_probability": round(jump, 3),
                                 "avoid_topics": [a.get("topic") for a in avoid[:3]],
                                 "dominant_causes": bias.get("dominant_causes", {})})
    return None


def _urgency(f: Finding) -> float:
    """Normalize heterogeneous findings onto one comparison scale (>=1.0 means firing), so the single
    most urgent bottleneck can be selected the way the global workspace selects one winner."""
    k = f.kind
    if k == "slow_span":
        return f.severity / Z_HOT
    if k == "high_failure":
        return f.severity / ABSTAIN_HOT
    if k == "overload":
        return f.severity / RSS_HOT
    if k == "commitment_thrash":
        return f.severity / DEBT_HOT
    if k == "failure_concentration":
        return f.severity / CONC_HOT
    return f.severity


# ---------------------------------------------------------------- the controller

@dataclass
class Decision:
    """The outcome of one watch-decide-resteer tick."""
    action: ActionResult
    finding: Finding | None
    snapshot: dict[str, Any]
    efficiency: float
    at: float = field(default_factory=time.time)

    @property
    def directive(self) -> dict[str, Any]:
        return self.action.directive

    @property
    def policy(self) -> str:
        return self.action.policy

    def as_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "directive": self.directive, "efficiency": round(self.efficiency, 3),
                "finding": None if self.finding is None else {"kind": self.finding.kind,
                                                              "span": self.finding.span,
                                                              "severity": self.finding.severity,
                                                              "repeat": self.finding.repeat},
                "snapshot": self.snapshot, "note": self.action.note}


class EfficiencyController:
    """Watch -> detect -> re-steer, over ATANOR's own processing. Stateless across ticks except for the
    persisted baselines and the decision ledger it reads for repeat-counting — so it survives restarts."""

    def __init__(self, repeat_window: int = 40, organ_judges: bool = True):
        self.repeat_window = repeat_window
        # organ_judges=False makes the controller purely span-driven (reproducible, independent of the
        # live self's incidental vitals) — used by the demo/tests so the proof is deterministic.
        self.organ_judges = organ_judges

    # -- repeat counting (persistence of an anomaly across ticks) --
    def _repeat(self, kind: str, span: str) -> int:
        try:
            rows = recent_decisions(self.repeat_window)
            return sum(1 for r in rows if r.get("kind") == kind and r.get("span") == span)
        except Exception:
            return 0

    # -- gather organ-level findings from the live snapshot --
    def _organ_findings(self, snap: dict[str, Any]) -> list[Finding]:
        out: list[Finding] = []
        if not self.organ_judges:
            return out
        for judge, key, span in (
            (lambda: judge_failures(snap, repeat=self._repeat("high_failure", "*")), "high_failure", "*"),
            (lambda: judge_overload(snap, repeat=self._repeat("overload", "process")), "overload", "process"),
            (lambda: judge_thrash(snap, repeat=self._repeat("commitment_thrash", "workspace")), "commitment_thrash", "workspace"),
            (lambda: judge_concentration(repeat=self._repeat("failure_concentration", "search")), "failure_concentration", "search"),
        ):
            try:
                f = judge()
            except Exception:
                f = None
            if f is not None:
                out.append(f)
        return out

    def _efficiency(self, snap: dict[str, Any], worst: Finding | None) -> float:
        """A derived control index in [0,1]: the MIN of the measured component healths (the weakest
        link dominates, like the loudest discomfort). Missing sensors are simply skipped, not faked."""
        healths: list[float] = []
        fr = snap.get("recent_failure_rate")
        if fr is not None:
            healths.append(max(0.0, 1.0 - float(fr)))
        p = snap.get("rss_pressure")
        if p is not None:
            healths.append(max(0.0, 1.0 - float(p)))
        debt = snap.get("commitment_debt")
        if debt is not None:
            healths.append(1.0 / (1.0 + float(debt) / DEBT_SCALE))
        coh = snap.get("coherence")
        if coh is not None:
            healths.append(max(0.0, min(1.0, float(coh))))
        if worst is not None and worst.kind == "slow_span":
            sig = float(worst.evidence.get("sigma", worst.severity))
            healths.append(max(0.0, 1.0 - sig / (2.0 * Z_HOT)))
        return round(min(healths), 3) if healths else 1.0

    def _resolve(self, findings: list[Finding], snap: dict[str, Any],
                 context: dict[str, Any] | None) -> Decision:
        worst = max(findings, key=_urgency) if findings else None
        result = resolve(worst, snap, context)
        journal_decision(result, worst, snap)
        return Decision(action=result, finding=worst, snapshot=snap,
                        efficiency=self._efficiency(snap, worst))

    # -- the daemon heartbeat: judge organ-level state, re-steer if needed --
    def decide(self, context: dict[str, Any] | None = None) -> Decision:
        if not mec_on():
            return Decision(action=resolve(None), finding=None, snapshot={}, efficiency=1.0)
        snap = snapshot()
        return self._resolve(self._organ_findings(snap), snap, context)

    # -- the inline per-span path: judge THIS span against its baseline, then fold + re-steer --
    def observe(self, name: str, ms: float, ok: bool = True, meta: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None) -> Decision:
        """Report a span AND get a re-steer decision. The span is judged against the baseline as it
        stands BEFORE this sample is folded in (textbook: the outlier is measured against history, not
        against a history that already contains it), then recorded."""
        if not mec_on():
            return Decision(action=resolve(None), finding=None, snapshot={}, efficiency=1.0)
        bl = Baselines.load()
        repeat = self._repeat("slow_span", name)
        span_finding = judge_span(bl, name, ms, ok, repeat=repeat)
        record_span(name, ms, ok=ok, meta=meta)             # fold + journal AFTER judging
        snap = snapshot()
        findings = ([span_finding] if span_finding else []) + self._organ_findings(snap)
        return self._resolve(findings, snap, context)

    # -- the attention-schema-for-control self-model + report --
    def schema(self) -> dict[str, Any]:
        """A simplified, reportable model of ATANOR's OWN processing right now — and, crucially, its
        LIMITS (what it is NOT watching), which is what makes it a schema of attention rather than the
        attention itself. This is the AST object, on the processing/efficiency axis."""
        snap = snapshot()
        bl = Baselines.load()
        monitored = sorted(k for k, v in bl.spans.items() if v.n >= MIN_SAMPLES)
        worst = max(self._organ_findings(snap), key=_urgency, default=None)
        return {
            "at": snap["at"],
            "efficiency": self._efficiency(snap, worst),
            "bottleneck": None if worst is None else worst.kind,
            "monitoring": monitored,
            "monitoring_count": len(monitored),
            # the schema owns its blind spots: MEC only sees what is instrumented + the few organ vitals
            "not_monitoring": "any processing not wrapped with a span, and any organ without a live sensor",
            "epistemic_status": ("This is a simplified self-model of my own processing efficiency, used "
                                 "to steer it. It is a control instrument; it makes no claim to feeling."),
        }

    def report(self, decision: Decision | None = None) -> str:
        """Metacognitive self-report generated FROM the schema/decision — the awareness-talk analogue,
        on the efficiency axis. Speaks only what was measured."""
        d = decision or self.decide()
        if d.finding is None or d.policy == "steady":
            return (f"No actionable inefficiency in my processing right now "
                    f"(efficiency index {d.efficiency:.2f}); not intervening.")
        f = d.finding
        return (f"My processing feels inefficient: {f.kind} on '{f.span}' "
                f"(efficiency {d.efficiency:.2f}). {d.action.note}.")


# ---------------------------------------------------------------- module-level convenience (daemons/pipelines)
_CONTROLLER = EfficiencyController()


def observe(name: str, ms: float, ok: bool = True, meta: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None) -> Decision:
    return _CONTROLLER.observe(name, ms, ok, meta, context)


def watch_tick(context: dict[str, Any] | None = None) -> Decision:
    """One heartbeat for a daemon to call: read the live self, re-steer if a judge fires."""
    return _CONTROLLER.decide(context)


def schema() -> dict[str, Any]:
    return _CONTROLLER.schema()


def report(decision: Decision | None = None) -> str:
    return _CONTROLLER.report(decision)
