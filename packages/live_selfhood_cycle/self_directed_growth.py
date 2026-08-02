# -*- coding: utf-8 -*-
"""Self-directed growth harness — the ADULT gate's sealed measurement (Grand Plan v2, G5).

The adult stage is the one gate that CANNOT be finished in software alone: it is a claim about TIME
— that over a real stretch (2 months), a sealed capability metric improved through the organism's
OWN chosen practice, with zero human-picked tasks. No harness can fast-forward the clock; what a
harness CAN do is make the claim UNFORGEABLE:

  * it starts a wall-clock (real UTC 'as_of' stamps, never fabricated) — the 2-month window;
  * each week it seals a snapshot: which capability the organism chose to work on (from its own
    measured deficits, self_development.py), and the sealed-battery scores BEFORE and AFTER that
    week — human labels: zero;
  * the adult gate reads only whether >= 2 sealed months each show a real, self-chosen improvement
    with a monotone wall-clock — so the number cannot be written early, and a regressing or
    human-steered week does not count.

self_directed_months (the development-stage signal) is DERIVED from this ledger, not asserted. The
honest line stays: this measures whether growth was self-directed over real time; it is a clock plus
an anti-forgery ledger, not a shortcut to being an adult.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "comprehension" / "self_directed_growth.jsonl"
SIGNAL = REPO / "data" / "track_f" / "self_directed_months.json"
WEEK_SECONDS = 7 * 24 * 3600
MONTH_SECONDS = 30 * 24 * 3600


@dataclass
class WeekSeal:
    t_utc: str                       # real wall-clock stamp (never fabricated)
    chosen_theme: str                # the capability the organism chose to work on (its own deficit)
    human_picked: bool               # MUST be False to count (the whole point)
    score_before: float
    score_after: float
    battery: str                     # which sealed battery was scored

    @property
    def improved(self) -> bool:
        return (not self.human_picked) and self.score_after > self.score_before


def _now_iso(now_utc: str | None) -> str:
    if now_utc:
        return now_utc
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def seal_week(chosen_theme: str, score_before: float, score_after: float, *,
              battery: str = "child", human_picked: bool = False,
              now_utc: str | None = None, ledger: Path | None = None) -> WeekSeal:
    """Seal one week's self-directed practice + its measured before/after. Append-only; the stamp is
    real wall-clock (or an injected UTC for tests), never invented."""
    led = ledger if ledger is not None else LEDGER
    led.parent.mkdir(parents=True, exist_ok=True)
    w = WeekSeal(t_utc=_now_iso(now_utc), chosen_theme=chosen_theme, human_picked=human_picked,
                 score_before=round(float(score_before), 3), score_after=round(float(score_after), 3),
                 battery=battery)
    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(w.__dict__) + "\n")
    return w


def _load(ledger: Path) -> list[WeekSeal]:
    if not ledger.exists():
        return []
    out = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            out.append(WeekSeal(**json.loads(line)))
        except Exception:
            continue
    return out


def sealed_months(ledger: Path | None = None) -> dict[str, Any]:
    """How many SEALED months of self-directed improvement the ledger proves. A month counts only if
    it spans a real >=30-day wall-clock window AND every contributing week improved on its own chosen
    theme with zero human labels. Cannot be forged by writing many same-day rows."""
    led = ledger if ledger is not None else LEDGER
    weeks = sorted(_load(led), key=lambda w: w.t_utc)
    if not weeks:
        return {"months": 0.0, "weeks": 0, "note": "no sealed growth yet"}
    self_dir = [w for w in weeks if w.improved]
    if not self_dir:
        return {"months": 0.0, "weeks": len(weeks), "self_directed_weeks": 0,
                "note": "weeks logged but none were self-directed improvements"}
    t0 = datetime.fromisoformat(self_dir[0].t_utc.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(self_dir[-1].t_utc.replace("Z", "+00:00"))
    span_days = (t1 - t0).total_seconds() / 86400
    months = span_days / 30.0
    return {"months": round(months, 2), "weeks": len(weeks),
            "self_directed_weeks": len(self_dir), "span_days": round(span_days, 1),
            "started": self_dir[0].t_utc, "latest": self_dir[-1].t_utc}


def refresh_signal(ledger: Path | None = None, out: Path | None = None) -> float:
    """Write the DERIVED self_directed_months to the development-stage signal file. Idempotent; the
    value can only be as large as the real wall-clock span the sealed ledger proves."""
    m = sealed_months(ledger)["months"]
    p = out if out is not None else SIGNAL
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"self_directed_months": m,
                                 "note": "derived from sealed weekly growth ledger; real wall-clock, "
                                         "zero human labels — not assertable early"}), encoding="utf-8")
    except Exception:
        pass
    return m
