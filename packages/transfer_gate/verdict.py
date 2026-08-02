# -*- coding: utf-8 -*-
"""Re-run a frozen domain and say, without hedging, whether anything transferred.

Named `verdict` and not `measure`, which is what it was first called: re-exporting the function
`measure` at package level rebinds that attribute on the package, so the MODULE became
unreachable by its own name -- `import packages.transfer_gate.measure` returned the function.
Same shape as the `acquisition_daemon/queue.py` stdlib shadow. Fixed at the source rather than
worked around at the call sites.

The verdict vocabulary is deliberately four-valued, because collapsing it to pass/fail is where a
test like this normally dies:

    INVALID    B's surface changed. The comparison means nothing. This is NOT "no change" -- a
               silent failure and a real null result look identical from the outside, and only one
               of them is evidence.
    IMPROVED   at least one pre-registered metric moved the way it was declared to, and none
               regressed.
    UNCHANGED  nothing moved beyond tolerance. A real, reportable outcome.
    REGRESSED  something moved the wrong way. Reported first and loudest, because consolidation
               breaking a domain it did not touch is the most important thing this gate can find.

Note what IMPROVED does not say: it does not say the consolidation caused it. It says B, untouched,
measures better than its sealed baseline while the shared substrate changed. That is the strongest
claim the instrument can support, and stating more would be the thing this instrument exists to
prevent.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.transfer_gate.manifest import (
    REPO, SEALED, FrozenDomain, commits_touching, hash_surface, load, seal_intact)

RESULTS = SEALED / "results.jsonl"

INVALID, IMPROVED, UNCHANGED, REGRESSED = "INVALID", "IMPROVED", "UNCHANGED", "REGRESSED"


@dataclass(frozen=True)
class MetricMove:
    name: str
    baseline: float
    now: float
    direction: str
    verdict: str                       # improved | unchanged | regressed

    @property
    def delta(self) -> float:
        return round(self.now - self.baseline, 6)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "baseline": self.baseline, "now": self.now,
                "delta": self.delta, "direction": self.direction, "verdict": self.verdict}


@dataclass(frozen=True)
class TransferVerdict:
    domain: str
    verdict: str
    moves: tuple[MetricMove, ...] = field(default_factory=tuple)
    surface_intact: bool = True
    seal_intact: bool = True
    commits_since_freeze: tuple[str, ...] = field(default_factory=tuple)
    measured_at: str = ""
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.verdict != INVALID

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "verdict": self.verdict,
                "moves": [m.to_dict() for m in self.moves],
                "surface_intact": self.surface_intact, "seal_intact": self.seal_intact,
                "commits_since_freeze": list(self.commits_since_freeze),
                "measured_at": self.measured_at, "reason": self.reason, "usable": self.usable}


def _resolve(entry: str):
    mod, _, fn = entry.partition(":")
    return getattr(importlib.import_module(mod), fn)


def measure(name: str, *, tolerance: float = 0.0, root: Path | None = None,
            path: Path | None = None, record: bool = True) -> TransferVerdict:
    """Re-run B's own sealed evaluation and compare against its pre-registered baseline."""
    r = root or REPO
    domain = load(name, path=path)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if domain is None:
        return TransferVerdict(name, INVALID, measured_at=stamp,
                               reason="no sealed manifest for this domain")

    ok_seal = seal_intact(domain)
    now_hash = hash_surface(domain.surface, r)
    ok_surface = now_hash == domain.surface_hash
    touched = tuple(commits_touching(domain.surface, domain.frozen_at, r))

    if not ok_seal or not ok_surface:
        why = ("the manifest was edited after freezing" if not ok_seal
               else "B's own surface changed after freezing; this is editing the exam, not transfer")
        return TransferVerdict(name, INVALID, surface_intact=ok_surface, seal_intact=ok_seal,
                               commits_since_freeze=touched, measured_at=stamp, reason=why)

    try:
        got = _resolve(domain.eval_entry)() or {}
    except Exception as exc:
        return TransferVerdict(name, INVALID, surface_intact=True, seal_intact=True,
                               commits_since_freeze=touched, measured_at=stamp,
                               reason=f"B's sealed evaluation did not run: {type(exc).__name__}: {exc}")

    moves: list[MetricMove] = []
    for m in domain.metrics:
        if m.name not in got:
            return TransferVerdict(
                name, INVALID, surface_intact=True, seal_intact=True,
                commits_since_freeze=touched, measured_at=stamp,
                reason=f"the evaluation no longer reports the pre-registered metric {m.name!r}")
        now = float(got[m.name])
        verdict = ("improved" if m.improved(now, tolerance=tolerance)
                   else "regressed" if m.regressed(now, tolerance=tolerance) else "unchanged")
        moves.append(MetricMove(m.name, m.baseline, now, m.direction, verdict))

    kinds = {mv.verdict for mv in moves}
    # Regression is reported first even when something else improved: a consolidation that breaks
    # an untouched domain is the most important thing this gate can find, and averaging it away
    # against a win is how that finding would be lost.
    overall = (REGRESSED if "regressed" in kinds
               else IMPROVED if "improved" in kinds else UNCHANGED)

    out = TransferVerdict(name, overall, tuple(moves), True, True, touched, stamp,
                          reason="B untouched; shared substrate free to change")
    if record:
        try:
            RESULTS.parent.mkdir(parents=True, exist_ok=True)
            with RESULTS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(out.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass
    return out


def history(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Every verdict ever taken, in order. Kept because a gate whose earlier readings can vanish is
    a gate that can be re-rolled until it passes."""
    src = path or RESULTS
    try:
        return [json.loads(ln) for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
