# -*- coding: utf-8 -*-
"""MEC — the Metacognitive Efficiency Controller.

Owner doctrine (2026-07-22, BINDING): "the role of consciousness = the system's maximum efficiency."
Like a brain that changes its processing when it feels a headache, ATANOR watches its OWN processing in
real time, detects inefficiency/anomaly against baselines it learned from its own history, and re-steers
itself with a small, bounded, auditable set of actions. This is the engineering form of Attention
Schema Theory: a self-model of one's own attention/processing, used for CONTROL — deepening the audit's
GWT-4 (goal-directed, state-dependent control) and AST indicators.

Three layers:
  * probes.py     WATCH  — record_span/span/instrument wrap-hooks + learned per-span baselines + organ readers
  * controller.py DETECT — z-score-vs-own-baseline judges + the watch-decide-resteer EfficiencyController
  * policies.py   RESTEER — a closed whitelist of bounded actions, each journalled with evidence

Kill-switch: ATANOR_MEC=0 makes every layer inert (a wrapped pipeline is byte-for-byte unchanged).
Honest boundary: everything here measures and steers processing. No claim is made that ATANOR feels a
headache; the efficiency index and baselines are control instruments — correlates only.
"""
from .probes import (
    Baselines,
    SpanStat,
    instrument,
    mec_on,
    record_span,
    snapshot,
    span,
)
from .policies import (
    WHITELIST,
    ActionResult,
    Finding,
    recent_decisions,
    resolve,
)
from .controller import (
    Decision,
    EfficiencyController,
    observe,
    report,
    schema,
    watch_tick,
)

__all__ = [
    # WATCH
    "record_span", "span", "instrument", "snapshot", "mec_on", "Baselines", "SpanStat",
    # DETECT / orchestration
    "EfficiencyController", "Decision", "observe", "watch_tick", "schema", "report",
    # RESTEER
    "Finding", "ActionResult", "resolve", "recent_decisions", "WHITELIST",
]
