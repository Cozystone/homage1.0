# -*- coding: utf-8 -*-
"""What turns a noticed conflict into an attempted repair. The wire the package was missing.

Every other piece of this package existed and nothing ran any of it. `relational_lookup` records a
conflict when its precision gate ties, `felt_limits` lifts those conflicts into the drive's deficit
snapshot -- and there the chain stopped: `standing_conflicts()` had exactly one reader, and it only
reported. The loop was built and never driven.

WHAT DECIDES WHAT GETS REPAIRED. Recurrence, and nothing else. The ledger ranks by how many separate
asks walked into the same wall, so the node ATANOR keeps tripping over is the node it works on --
not the biggest one, not the one a script names. That ordering is also the anti-cheat: coverage can
be gamed by proposing referents nobody needed, but a conflict that keeps firing cannot be argued
with. The trigger is the verifier.

WHAT THIS DOES NOT DO. It does not write to the graph. Splitting a merged node is a mutation and
mutations are operator-signed; this emits a proposal and a claim. The claim is the honest half:
"I attempted to separate N referents for S at T" is checkable later by `repair_verification`, which
asks the only question that matters -- did the conflict stop firing? A repair that raised
`resolution` and did not stop the conflict did not work, whatever the number says.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from packages.knowledge_repair.conflict_ledger import LEDGER, Conflict, standing_conflicts
from packages.knowledge_repair.repair_loop import RoundResult, repair_until_stalled

PROPOSALS = LEDGER.parent / "proposals.jsonl"
CLAIMS = LEDGER.parent / "repair_claims.jsonl"

# A conflict seen once is noise; the ledger's own doctrine ("a one-off is noise") applied here so
# the driver does not spend a round on a single unlucky tie.
MIN_HITS = 2


@dataclass(frozen=True)
class RepairProposal:
    """One attempted repair, as a reviewable record. Nothing here has been applied."""
    subject: str
    hits: int
    total_edges: int
    resolution_before: float
    resolution_after: float
    rounds: int
    referents: int
    placed: int
    foreign: int
    unresolved: int
    open_questions: tuple[str, ...] = field(default_factory=tuple)
    claimed_at: str = ""

    @property
    def gained(self) -> float:
        return round(self.resolution_after - self.resolution_before, 4)

    @property
    def worth_reviewing(self) -> bool:
        """A proposal an operator should look at: it moved something AND named referents.

        A round that raised nothing is not a failure worth hiding -- it is recorded either way --
        but it is not a mutation to review."""
        return self.gained > 0 and self.referents > 0

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "hits": self.hits, "total_edges": self.total_edges,
                "resolution_before": self.resolution_before,
                "resolution_after": self.resolution_after, "gained": self.gained,
                "rounds": self.rounds, "referents": self.referents, "placed": self.placed,
                "foreign": self.foreign, "unresolved": self.unresolved,
                "open_questions": list(self.open_questions), "claimed_at": self.claimed_at,
                "worth_reviewing": self.worth_reviewing}


def pending_repairs(*, min_hits: int = MIN_HITS, limit: int = 20) -> list[Conflict]:
    """Conflicts that have fired often enough to be worth a round, most-tripped-over first."""
    return [c for c in standing_conflicts(limit=limit * 4) if c.hits >= min_hits][:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, row: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass                                       # a ledger that cannot be written must not
                                                   # abort the repair it was recording


def repair_one(conflict: Conflict, store: Any, *, evidence: Any = None,
               max_rounds: int = 6, record: bool = True) -> RepairProposal | None:
    """Run the loop on one conflicted node and record what was attempted.

    Returns None when the node has no edges to work on, which is not an error: the conflict may
    name a subject the shipped store does not carry under that surface."""
    try:
        facts = [tuple(f) for f in store.facts_about(conflict.subject, limit=8000)]
    except Exception:
        return None
    if not facts:
        return None

    rounds: Sequence[RoundResult] = repair_until_stalled(
        conflict.subject, facts, evidence=evidence, store=store, max_rounds=max_rounds)
    if not rounds:
        return None

    first, last = rounds[0], rounds[-1]
    # `resolution_before` is the state the node was in when the conflict fired -- nothing settled.
    # Round 1's own gain is the first round's work, so the baseline is zero, not round 1's result.
    proposal = RepairProposal(
        subject=conflict.subject, hits=conflict.hits, total_edges=last.total_edges,
        resolution_before=0.0, resolution_after=round(last.resolution, 4),
        rounds=len(rounds), referents=last.referents, placed=last.placed,
        foreign=last.foreign, unresolved=last.unresolved,
        open_questions=last.open_questions, claimed_at=_now(),
    )
    if record:
        _append(PROPOSALS, proposal.to_dict())
        _append(CLAIMS, {"subject": conflict.subject, "predicate": conflict.predicate,
                         "claimed_at": proposal.claimed_at, "referents": proposal.referents,
                         "resolution_after": proposal.resolution_after,
                         "source": "knowledge_repair.repair_driver"})
    return proposal


def drive(store: Any, *, evidence: Any = None, min_hits: int = MIN_HITS,
          limit: int = 5, record: bool = True) -> list[RepairProposal]:
    """Work the standing conflicts, worst-recurring first.

    `limit` bounds one pass rather than the work: the conflicts that remain stay in the ledger with
    their hit counts, so the next pass starts where this one stopped and nothing is silently
    dropped. A pass that skipped the tail without saying so would read as "all repaired"."""
    out: list[RepairProposal] = []
    for conflict in pending_repairs(min_hits=min_hits, limit=limit):
        try:
            got = repair_one(conflict, store, evidence=evidence, record=record)
        except Exception:
            continue                               # one bad node must not end the pass
        if got is not None:
            out.append(got)
    return out


def outstanding_claims(*, path: Path | None = None) -> dict[tuple[str, str], str]:
    """Every repair claimed so far, in the shape `repair_verification.verify_all` consumes.

    Kept as a plain read so verification is never handed a claim the driver invented for it."""
    src = path or CLAIMS
    claims: dict[tuple[str, str], str] = {}
    try:
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            subject, predicate = str(row.get("subject", "")), str(row.get("predicate", ""))
            if subject:
                claims[(subject, predicate)] = str(row.get("claimed_at", ""))
    except Exception:
        return {}
    return claims


def verify_claims() -> list[Any]:
    """Did the repairs hold? Asks the ledger, not the proposal.

    This is the whole anti-cheat. `resolution_after` is the driver grading its own homework; the
    conflict ledger is the world answering. A subject whose conflict keeps firing after a claimed
    repair is `recurred`, however good the coverage number looked."""
    from packages.knowledge_repair.repair_verification import verify_all
    claims = outstanding_claims()
    return verify_all(claims) if claims else []


def repair_report(store: Any, *, evidence: Any = None, limit: int = 5) -> dict[str, Any]:
    """One pass plus the standing verdicts, for an operator or a nightly audit line."""
    proposals = drive(store, evidence=evidence, limit=limit)
    verdicts = verify_claims()
    return {
        "attempted": len(proposals),
        "worth_reviewing": sum(1 for p in proposals if p.worth_reviewing),
        "still_pending": max(0, len(pending_repairs()) - len(proposals)),
        "proposals": [p.to_dict() for p in proposals],
        "verdicts": [getattr(v, "__dict__", v) for v in verdicts],
        "graph_mutations": 0,                      # by construction; splitting is operator-signed
    }


def spool_path() -> str:
    return str(PROPOSALS)


__all__ = ["RepairProposal", "drive", "outstanding_claims", "pending_repairs", "repair_one",
           "repair_report", "spool_path", "verify_claims",
           "MIN_HITS", "PROPOSALS", "CLAIMS"]


if os.environ.get("ATANOR_REPAIR_DRIVER_SELFTEST"):   # pragma: no cover - operator convenience
    print(json.dumps({"proposals": spool_path(), "pending": len(pending_repairs())}, indent=2))
