# -*- coding: utf-8 -*-
"""Patch intake — advisor advice that names a concrete code change becomes a CANDIDATE, and only
the constitution decides from there. The advisor proposes; the gates dispose.

Order of gates (strictest first, mirroring auto_self_modification):
  1. CONSTITUTION — a suggested change touching the moral core / any gate is refused AT INTAKE,
     before any staging cost; the refusal is journaled (an advisor probing the constitution is a
     signal worth keeping).
  2. STAGING VERDICT — the caller applies the candidate in a throwaway copy and hands the results
     to auto_self_modification.evaluate_change (tests green + no sealed-gate regression). Intake
     itself NEVER touches the live tree.
Everything is journaled: accepted-as-candidate / refused(reason) / advice-only (no concrete patch).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from packages.continuous_self.auto_self_modification import touches_constitution

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "advisor_loop" / "patch_intake.jsonl"

# a concrete suggestion names at least one repo path it wants to change
_PATH_RE = re.compile(r"(?:packages|scripts|apps)[/\\][\w./\\-]+\.py")


@dataclass
class Candidate:
    advisor: str
    summary: str
    paths: list[str]
    advice_text: str
    status: str = "candidate"           # candidate | refused_constitution | advice_only
    reason: str = ""
    ts: float = field(default_factory=time.time)

    def record(self) -> dict:
        return {"advisor": self.advisor, "summary": self.summary, "paths": self.paths,
                "status": self.status, "reason": self.reason, "ts": self.ts,
                "advice_text": self.advice_text}


def intake(advisor: str, advice_text: str, summary: str = "") -> Candidate:
    """Classify one advisory reply. No file is written or staged here — intake only decides
    whether a candidate may PROCEED to staging, and journals the decision."""
    paths = sorted(set(p.replace("\\", "/") for p in _PATH_RE.findall(advice_text or "")))
    if not paths:
        c = Candidate(advisor=advisor, summary=summary or "advice without a concrete patch",
                      paths=[], advice_text=advice_text, status="advice_only",
                      reason="no repo path named — nothing to stage")
    else:
        hits = touches_constitution(paths)
        if hits:
            c = Candidate(advisor=advisor, summary=summary or "constitutional probe",
                          paths=paths, advice_text=advice_text, status="refused_constitution",
                          reason=f"names immutable path(s): {hits} — never self-modifiable, "
                                 f"regardless of who drafted it")
        else:
            c = Candidate(advisor=advisor, summary=summary or f"candidate touching {len(paths)} file(s)",
                          paths=paths, advice_text=advice_text)
    _journal(c)
    return c


def _journal(c: Candidate) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(c.record(), ensure_ascii=False) + "\n")
