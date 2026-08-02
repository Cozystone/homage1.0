# -*- coding: utf-8 -*-
"""Trust a capability has EARNED by being right about itself, per capability, from its own record.

The owner's intent (2026-07-28): relax the constraints progressively as ATANOR becomes
trustworthy, rather than keeping a fixed whitelist forever. That needs a basis. Time served is not
one -- a system that has been running a year without being measured has earned nothing.
`CapabilityWhitelist` is a fixed frozenset an operator edits, so today there is no record that
could justify widening it.

WHAT IS MEASURED: calibration, not success. The question is not "did the action work" but "when it
said it was confident, was it right". A capability that succeeds 60% of the time and SAYS 60% is
trustworthy and can be given room. One that succeeds 95% while claiming 100% is not, because the
5% arrives unannounced -- and an unannounced failure is the one that cannot be caught.

WHY CALIBRATION RESISTS GAMING, which is the point of choosing it. To inflate this score a
capability must make predictions that the world then confirms. Claiming confidence it does not
have makes the score WORSE the moment reality answers. The only way to raise it is to actually
become more predictable -- which is the behaviour we wanted. Contrast a success-rate score, which
is trivially raised by attempting only easy things, and a self-reported score, which is raised by
lying.

  * outcomes are recorded by whatever OBSERVED them, never by the actor;
  * `earned_scope` reports; it grants nothing. Widening the envelope stays an operator act, and
    this exists so that act can rest on evidence instead of a feeling.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "autonomy_envelope" / "earned_trust.jsonl"

# Below this many observations a rate is noise, so no scope is reported either way. Silence is the
# correct output for "not enough evidence" -- the failure mode to avoid is a capability earning
# freedom from three lucky trials.
MIN_OBSERVATIONS = 30


@dataclass(frozen=True)
class TrustRecord:
    """What one capability's own record says about how much it can be believed."""
    capability: str
    observations: int
    confident_claims: int
    confident_correct: int
    abstentions: int

    @property
    def precision_when_confident(self) -> float:
        """Of the times it claimed confidence, how often was it right. This is the number that
        matters: a wrong answer delivered confidently is the failure autonomy cannot absorb."""
        return self.confident_correct / self.confident_claims if self.confident_claims else 0.0

    @property
    def overconfidence(self) -> float:
        """How far its confident claims fall short of being right. 0.0 is calibrated."""
        return max(0.0, 1.0 - self.precision_when_confident)

    @property
    def abstention_rate(self) -> float:
        return self.abstentions / self.observations if self.observations else 0.0

    @property
    def sufficient_evidence(self) -> bool:
        return self.observations >= MIN_OBSERVATIONS and self.confident_claims > 0

    def as_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "observations": self.observations,
                "confident_claims": self.confident_claims,
                "precision_when_confident": round(self.precision_when_confident, 4),
                "overconfidence": round(self.overconfidence, 4),
                "abstention_rate": round(self.abstention_rate, 4),
                "sufficient_evidence": self.sufficient_evidence}


def record_outcome(capability: str, *, claimed_confident: bool, was_correct: bool | None,
                   observer: str, note: str = "") -> None:
    """Log one observed outcome. `observer` is who checked -- never the actor itself.

    `was_correct=None` marks an abstention: it has no correctness, and counting an abstention as a
    success would reward saying nothing, which is the cheapest way to look calibrated."""
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "capability": str(capability)[:120],
               "claimed_confident": bool(claimed_confident),
               "was_correct": None if was_correct is None else bool(was_correct),
               "observer": str(observer)[:80], "note": str(note)[:200]}
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def trust_records(path: Path | None = None) -> list[TrustRecord]:
    """Per-capability calibration, read off the ledger."""
    agg: dict[str, list[int]] = {}
    try:
        for line in (path or LEDGER).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            cap = str(r.get("capability", ""))
            if not cap:
                continue
            a = agg.setdefault(cap, [0, 0, 0, 0])          # obs, claims, correct, abstentions
            a[0] += 1
            if r.get("was_correct") is None:
                a[3] += 1
            elif r.get("claimed_confident"):
                a[1] += 1
                a[2] += int(bool(r.get("was_correct")))
    except OSError:
        return []
    return sorted((TrustRecord(c, *v) for c, v in agg.items()),
                  key=lambda t: (-t.precision_when_confident, -t.observations))


def earned_scope(max_overconfidence: float = 0.05, path: Path | None = None) -> dict[str, Any]:
    """Which capabilities their own record would support relaxing, and which it argues against.

    REPORTS ONLY. Nothing here widens an envelope, and it deliberately cannot: a system that could
    grant itself scope by writing its own ledger would be measuring nothing. The operator decides;
    this supplies the evidence that decision was missing."""
    recs = trust_records(path)
    ready, not_ready, insufficient = [], [], []
    for r in recs:
        if not r.sufficient_evidence:
            insufficient.append(r.as_dict())
        elif r.overconfidence <= max_overconfidence:
            ready.append(r.as_dict())
        else:
            not_ready.append(r.as_dict())
    return {"max_overconfidence": max_overconfidence, "min_observations": MIN_OBSERVATIONS,
            "supports_relaxing": ready, "argues_against": not_ready,
            "not_enough_evidence": insufficient,
            "grants_nothing": True}
