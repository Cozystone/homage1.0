# -*- coding: utf-8 -*-
"""Probes — the WATCH layer of the Metacognitive Efficiency Controller (MEC).

Owner doctrine (2026-07-22, BINDING): "the role of consciousness = the system's maximum efficiency."
A brain that feels a headache re-steers its own processing. The engineering form is Attention Schema
Theory taken one step past reporting: a system keeps a simplified MODEL of its own processing and uses
that model for CONTROL. This module is the model's sensory surface — it measures ATANOR's OWN
processing, honestly, from real signals only.

Two intake paths, both pure observation (they never change what the wrapped pipeline returns):
  * record_span(name, ms, ok, meta) — a wrap-hook a pipeline calls to report one unit of work: how
    long it took, whether it succeeded, and a little context. Appended to a bounded span journal and
    folded into a per-span rolling BASELINE (Welford online mean/variance) so the system learns what
    "normal" is for each operation FROM ITS OWN HISTORY, persisted across restarts.
  * organ readers — coherence vital (stakes), commitment/queue debt (ignition), memory RSS
    (metabolism). These are READ from the live self, never invented; if a sensor is missing the read
    degrades to a declared-neutral value, never a fabricated event.

Kill-switch (ATANOR_MEC=0): every intake and the whole controller become inert — record_span does not
even journal, so a wrapped pipeline is byte-for-byte unchanged. The baseline is a LEARNED component
(online sufficient statistics), registered in packages/neuro_ledger with fact_source=False.

Honest boundary: this measures processing and models it for control. It makes no claim that ATANOR
feels a headache. The efficiency index and the baselines are control instruments; correlates only.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- control constants (declared)
# These are CONTROL-LOOP time-constants and thresholds — the same curated-structure category as
# homeostasis set-points and the stakes half-lives. They are not knowledge (knowledge lives in the
# graph); they are the controller's physiology, tuned to be conservative (intervene rarely).
MIN_SAMPLES = 8            # a baseline needs at least this much history before it may judge a span
DEV_FLOOR_FRAC = 0.15      # regularize the z-score: the deviation scale never falls below this * mean
                           # (so a dead-steady baseline with ~0 variance cannot manufacture huge z)
SPANS_MAX = 5000           # the span journal is a bounded ring — it remembers, but never grows without limit


def mec_on() -> bool:
    """The master kill-switch. ATANOR_MEC=0 freezes the whole organ (probes + controller + policies)."""
    return os.getenv("ATANOR_MEC", "1").strip().lower() not in ("0", "off", "false", "no")


def _base_dir() -> Path:
    """Where MEC keeps its journals + learned baselines. Overridable (ATANOR_METACOG_DIR) so tests
    isolate completely and the real self is never touched by a test run."""
    override = os.getenv("ATANOR_METACOG_DIR")
    base = Path(override) if override else (REPO / "data" / "metacog")
    return base


def spans_path() -> Path:
    return _base_dir() / "spans.jsonl"


def baselines_path() -> Path:
    return _base_dir() / "baselines.json"


# ---------------------------------------------------------------- per-span rolling baseline (learned)

@dataclass
class SpanStat:
    """Online sufficient statistics for one span-name (Welford). Not a trained weight — a running
    summary of the operation's own history, from which 'normal' and 'anomalous' are derived."""
    n: int = 0
    mean: float = 0.0          # mean latency (ms)
    m2: float = 0.0            # sum of squared deviations (Welford accumulator)
    ok_n: int = 0              # successes seen
    last_ms: float = 0.0
    updated: float = 0.0

    def update(self, ms: float, ok: bool) -> None:
        self.n += 1
        delta = ms - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (ms - self.mean)
        self.ok_n += 1 if ok else 0
        self.last_ms = ms
        self.updated = time.time()

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0

    @property
    def ok_rate(self) -> float:
        return self.ok_n / self.n if self.n else 1.0

    def dev_scale(self) -> float:
        """The regularized deviation scale: at least DEV_FLOOR_FRAC of the mean, so a baseline that
        happens to be nearly variance-free cannot report an astronomically large z for a small blip."""
        return max(self.std, DEV_FLOOR_FRAC * abs(self.mean), 1e-6)

    def severity(self, ms: float) -> float:
        """How far ABOVE its own normal this latency is, in regularized sigmas. Negative/zero = at or
        below normal (never an anomaly). Only meaningful once n >= MIN_SAMPLES."""
        if self.n < MIN_SAMPLES:
            return 0.0
        return (ms - self.mean) / self.dev_scale()

    def as_dict(self) -> dict[str, Any]:
        # mean and m2 are ACCUMULATORS reloaded before every online update; they are stored at full
        # precision (JSON doubles round-trip exactly) so rounding cannot drift the variance over time.
        return {"n": self.n, "mean": self.mean, "m2": self.m2,
                "ok_n": self.ok_n, "last_ms": round(self.last_ms, 4), "updated": round(self.updated, 2)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SpanStat":
        return cls(n=int(d.get("n", 0)), mean=float(d.get("mean", 0.0)), m2=float(d.get("m2", 0.0)),
                   ok_n=int(d.get("ok_n", 0)), last_ms=float(d.get("last_ms", 0.0)),
                   updated=float(d.get("updated", 0.0)))


@dataclass
class Baselines:
    """The learned baselines for every span-name, persisted as data/metacog/baselines.json."""
    spans: dict[str, SpanStat] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Baselines":
        p = baselines_path()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            spans = {k: SpanStat.from_dict(v) for k, v in raw.get("spans", {}).items()}
            return cls(spans=spans)
        except Exception:
            return cls()

    def save(self) -> None:
        p = baselines_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "component": "metacog.baselines",
                       "spans": {k: v.as_dict() for k, v in self.spans.items()}}
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
            tmp.replace(p)                                  # atomic-ish swap
        except Exception:
            pass

    def stat(self, name: str) -> SpanStat:
        return self.spans.get(name, SpanStat())

    def update(self, name: str, ms: float, ok: bool) -> SpanStat:
        st = self.spans.setdefault(name, SpanStat())
        st.update(ms, ok)
        return st


# ---------------------------------------------------------------- span intake (the wrap-hook)

def record_span(name: str, ms: float, ok: bool = True, meta: dict[str, Any] | None = None) -> None:
    """Report one unit of work. Pure observation: it journals the span and folds it into the learned
    baseline, and NOTHING else — it never raises, never blocks, never changes a caller's result. When
    the kill-switch is off it is a complete no-op (zero side effects), so wrapping a live pipeline with
    it can be proven to change nothing."""
    if not mec_on():
        return
    try:
        rec = {"ts": round(time.time(), 3), "name": str(name)[:80], "ms": round(float(ms), 3),
               "ok": bool(ok), "meta": meta or {}}
        p = spans_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _trim_ring(p, SPANS_MAX)
        bl = Baselines.load()
        bl.update(rec["name"], rec["ms"], rec["ok"])
        bl.save()
    except Exception:
        pass


def _trim_ring(p: Path, cap: int) -> None:
    """Keep the span journal bounded. Cheap: only rewrites when it has grown well past the cap."""
    try:
        if p.stat().st_size < 512:                          # tiny file — never worth scanning
            return
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > cap + cap // 5:                     # 20% hysteresis so we rewrite rarely
            p.write_text("\n".join(lines[-cap:]) + "\n", encoding="utf-8")
    except Exception:
        pass


class span:
    """Context manager that times a block and reports it via record_span. Pure observer: it re-raises
    any exception unchanged (recording ok=False first). Inert under the kill-switch.

        with span("base_brain.answer", meta={"lang": "en"}):
            ...
    """
    __slots__ = ("name", "meta", "_t0", "ok")

    def __init__(self, name: str, meta: dict[str, Any] | None = None):
        self.name = name
        self.meta = meta or {}
        self._t0 = 0.0
        self.ok = True

    def __enter__(self) -> "span":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        ms = (time.perf_counter() - self._t0) * 1000.0
        try:
            record_span(self.name, ms, ok=(exc_type is None), meta=self.meta)
        except Exception:
            pass
        return False                                        # never swallow the caller's exception


def instrument(name: str, *, ok_from=None):
    """Decorator form of `span` for wrapping a whole function as one live pipeline probe. Under the
    kill-switch it returns the function UNCHANGED (zero overhead, zero behaviour change).

    ok_from(result) -> bool lets a pipeline whose success is encoded in its return value (e.g. an
    answer dict with 'useful_answer') report a semantic success, not merely 'did not raise'."""
    def _decorate(fn):
        if not mec_on():
            return fn                                       # truly a pass-through when disabled

        def _wrapped(*args, **kwargs):
            t0 = time.perf_counter()
            ok = True
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception:
                ok = False
                raise
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                try:
                    if ok and ok_from is not None:
                        ok = bool(ok_from(result))
                except Exception:
                    pass
                record_span(name, ms, ok=ok, meta={"fn": getattr(fn, "__name__", str(name))})
        _wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        _wrapped.__doc__ = fn.__doc__
        _wrapped.__wrapped__ = fn
        return _wrapped
    return _decorate


# ---------------------------------------------------------------- recent-window rates (from journal)

def recent_spans(window: int = 50, name: str | None = None) -> list[dict[str, Any]]:
    """The tail of the span journal — the recent lived processing the judges read."""
    p = spans_path()
    if not p.exists():
        return []
    try:
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if name is None or r.get("name") == name:
                rows.append(r)
        return rows[-window:]
    except Exception:
        return []


def failure_rate(window: int = 50, name: str | None = None) -> tuple[float, int]:
    """Fraction of recent spans that did NOT succeed (ok=False, or meta.abstained=True), and the
    sample count. This is the 'retries/abstention' health of recent processing, measured not guessed."""
    rows = recent_spans(window, name)
    if not rows:
        return 0.0, 0
    bad = sum(1 for r in rows if (not r.get("ok", True)) or r.get("meta", {}).get("abstained"))
    return bad / len(rows), len(rows)


# ---------------------------------------------------------------- organ readers (read, never invented)

def read_coherence() -> float | None:
    """The coherence vital from stakes (S1) — 'how integrated am I' — as a discomfort input. None if
    the organ cannot be read (honest missing sensor, never a fabricated 1.0)."""
    try:
        from packages.continuous_self.stakes import read_vitals
        return float(read_vitals().coherence)
    except Exception:
        return None


def read_commitment_debt() -> int | None:
    """Open-commitment / workspace-queue depth from ignition (S2). A climbing debt means the serial
    workspace is starting more than it finishes — a real inefficiency (thrash)."""
    try:
        from packages.continuous_self.ignition import commitment_debt
        return int(commitment_debt())
    except Exception:
        return None


def read_rss() -> tuple[float, float] | None:
    """(rss_mb, pressure in [0,1]) from the metabolism budget — the compute wallet. None if unreadable."""
    try:
        from packages.continuous_self.metabolism import metabolic_state
        m = metabolic_state()
        return float(m.get("rss_mb", 0.0)), float(m.get("memory_pressure", 0.0))
    except Exception:
        return None


def snapshot(window: int = 50) -> dict[str, Any]:
    """The current WATCH reading — a compact, reportable model of ATANOR's own processing right now.
    Every field is measured from a real source or honestly marked missing (None)."""
    fr, n = failure_rate(window)
    coh = read_coherence()
    debt = read_commitment_debt()
    rss = read_rss()
    return {
        "at": round(time.time(), 3),
        "recent_failure_rate": round(fr, 4),
        "recent_samples": n,
        "coherence": None if coh is None else round(coh, 4),
        "commitment_debt": debt,
        "rss_mb": None if rss is None else round(rss[0], 1),
        "rss_pressure": None if rss is None else round(rss[1], 4),
    }
