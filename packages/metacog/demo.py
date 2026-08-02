# -*- coding: utf-8 -*-
"""Live proof — MEC detects an injected inefficiency from its OWN baseline and re-steers mid-run.

The experiment is a controlled A/B: the operation "demo.solve" can run on two strategies —
  * strategy B: fast and reliable (~3ms, no failures)          — the good lane
  * strategy A: slow and failing (~25ms, ~30% failures)        — the injected inefficiency

Both runs consume the SAME seeded task stream, so the only variable is MEC:
  1. Warm-up on B teaches MEC what "demo.solve" normally costs (a baseline from its own history).
  2. The workload is then routed to the slow lane A (a bad routing decision / a degraded dependency).
  3. WITH MEC: the first slow sample is many sigmas over the learned baseline -> the switch_strategy
     policy fires -> the runner returns to B mid-run -> throughput recovers.
     WITHOUT MEC (kill-switch): nothing watches, nothing switches -> the run stays stuck on A.

Throughput is measured from the recorded per-task milliseconds (deterministic; no real sleeps), so the
before/after numbers are reproducible. The headline is the ratio of MEC-on to MEC-off throughput on the
identical task stream — the efficiency the controller bought by re-steering.
"""
from __future__ import annotations

import os
import random
import tempfile
from dataclasses import dataclass, field
from typing import Any

from .controller import EfficiencyController
from .probes import record_span

# strategy profiles (declared workload parameters — this is a fixture, not knowledge)
_STRATEGIES = {
    "A": {"base_ms": 25.0, "jitter": 6.0, "fail_rate": 0.30},   # the injected slow/failing lane
    "B": {"base_ms": 3.0, "jitter": 0.8, "fail_rate": 0.0},     # the fast reliable lane
}
_SPAN = "demo.solve"


def _draw(strategy: str, rng: random.Random) -> tuple[float, bool]:
    p = _STRATEGIES[strategy]
    ms = max(0.1, p["base_ms"] + rng.uniform(-p["jitter"], p["jitter"]))
    ok = rng.random() >= p["fail_rate"]
    return round(ms, 3), ok


def _throughput(samples: list[tuple[float, bool]]) -> float:
    """Tasks per simulated second, from the recorded milliseconds. 0 for an empty window."""
    total_ms = sum(ms for ms, _ in samples)
    return round(len(samples) / (total_ms / 1000.0), 2) if total_ms > 0 else 0.0


def _failrate(samples: list[tuple[float, bool]]) -> float:
    return round(sum(1 for _, ok in samples if not ok) / len(samples), 3) if samples else 0.0


@dataclass
class DemoResult:
    switch_tick: int | None
    detection: dict[str, Any] | None
    mec_on_throughput: float
    mec_off_throughput: float
    pre_switch_throughput: float
    post_switch_throughput: float
    improvement: float
    mec_on_failrate: float
    mec_off_failrate: float
    baseline_mean_ms: float
    n_warm: int
    n_main: int
    report_lines: list[str] = field(default_factory=list)


def run_demo(n_warm: int = 40, n_main: int = 80, seed: int = 7) -> DemoResult:
    """Run the controlled experiment and return the measured before/after. Uses an isolated temp
    metacog dir so the real self's journals are never touched."""
    tmp = tempfile.mkdtemp(prefix="mec_demo_")
    prev_dir = os.environ.get("ATANOR_METACOG_DIR")
    prev_mec = os.environ.get("ATANOR_MEC")
    os.environ["ATANOR_METACOG_DIR"] = tmp
    os.environ["ATANOR_MEC"] = "1"
    try:
        # one shared, seeded task stream so MEC-on and MEC-off face the identical workload
        rng = random.Random(seed)
        warm_stream = [_draw("B", rng) for _ in range(n_warm)]
        main_A = [_draw("A", rng) for _ in range(n_main)]     # what the slow lane would produce each tick
        main_B = [_draw("B", rng) for _ in range(n_main)]     # what the fast lane would produce each tick

        # --- warm-up: teach MEC the healthy baseline for demo.solve (pure observation) ---
        for ms, ok in warm_stream:
            record_span(_SPAN, ms, ok=ok)
        from .probes import Baselines
        baseline_mean = round(Baselines.load().stat(_SPAN).mean, 3)

        # --- MEC ON: route to the slow lane A; let the controller re-steer ---
        # organ_judges=False -> the proof depends only on the span baseline (reproducible anywhere)
        ctrl = EfficiencyController(organ_judges=False)
        current = "A"
        switch_tick: int | None = None
        detection: dict[str, Any] | None = None
        on_samples: list[tuple[float, bool]] = []
        for i in range(n_main):
            ms, ok = (main_A[i] if current == "A" else main_B[i])
            dec = ctrl.observe(_SPAN, ms, ok,
                               context={"current": current, "alternatives": ["A", "B"]})
            on_samples.append((ms, ok))
            if switch_tick is None and dec.policy == "switch_strategy" and dec.directive.get("to"):
                switch_tick = i
                detection = {"tick": i, "policy": dec.policy, "note": dec.action.note,
                             "sigma": dec.finding.evidence.get("sigma") if dec.finding else None,
                             "efficiency": dec.efficiency, "directive": dec.directive}
                current = dec.directive["to"]

        # --- MEC OFF: identical task stream, no watcher -> stays on A the whole time ---
        off_samples = list(main_A)

        # the tick that DETECTS still ran lane A; the switch takes effect on the following tick
        if switch_tick is not None:
            pre = on_samples[:switch_tick + 1]
            post = on_samples[switch_tick + 1:]
        else:
            pre, post = on_samples, []
        res = DemoResult(
            switch_tick=switch_tick,
            detection=detection,
            mec_on_throughput=_throughput(on_samples),
            mec_off_throughput=_throughput(off_samples),
            pre_switch_throughput=_throughput(pre),
            post_switch_throughput=_throughput(post),
            improvement=round(_throughput(on_samples) / _throughput(off_samples), 2)
            if _throughput(off_samples) > 0 else 0.0,
            mec_on_failrate=_failrate(on_samples),
            mec_off_failrate=_failrate(off_samples),
            baseline_mean_ms=baseline_mean,
            n_warm=n_warm, n_main=n_main,
        )
        res.report_lines = _format(res)
        return res
    finally:
        for k, v in (("ATANOR_METACOG_DIR", prev_dir), ("ATANOR_MEC", prev_mec)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _format(r: DemoResult) -> list[str]:
    lines = [
        "MEC v0 live proof — inject slow lane A, MEC re-steers to fast lane B",
        f"  learned baseline for '{_SPAN}': {r.baseline_mean_ms} ms (from {r.n_warm} warm-up samples)",
    ]
    if r.detection:
        lines.append(f"  detected at tick {r.detection['tick']}: {r.detection['sigma']} sigma over baseline "
                     f"-> {r.detection['policy']} (efficiency {r.detection['efficiency']})")
    else:
        lines.append("  (no anomaly detected)")
    lines += [
        f"  pre-switch throughput (lane A):  {r.pre_switch_throughput} tasks/s  (fail {r.mec_on_failrate})",
        f"  post-switch throughput (lane B): {r.post_switch_throughput} tasks/s",
        f"  MEC ON  whole-run throughput: {r.mec_on_throughput} tasks/s (fail {r.mec_on_failrate})",
        f"  MEC OFF whole-run throughput: {r.mec_off_throughput} tasks/s (fail {r.mec_off_failrate})",
        f"  improvement (on/off, identical task stream): {r.improvement}x",
    ]
    return lines


if __name__ == "__main__":
    result = run_demo()
    print("\n".join(result.report_lines))
