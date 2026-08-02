# -*- coding: utf-8 -*-
"""The autonomous acquisition DAEMON — ATANOR's honest, safe OAM engine.

"저녁에 시키면 밤새 스스로 배워온다" — but SAFELY. Unattended, the daemon:
  (1) ENDOGENOUSLY detects the system's own knowledge gaps (``gap_signals.GapLedger``: real,
      recurring honest abstentions — pressure, not a timer);
  (2) runs the EXISTING acquisition loop (``knowledge_acquisition.acquire``) for each pressured gap
      against an evidence source, on a SCRATCH copy of the graph (never the shipped store);
  (3) accumulates every consensus-verified fact into an operator-approval QUEUE
      (``promotion_queue.AcquisitionQueue``) — it PROPOSES, it never auto-writes the shipped graph.

The shipped store is opened READ-ONLY for gap detection and is provably byte-unchanged after a run.
Nothing persists to a real store without the operator-signed gate (see
``promotion_queue.approve_and_apply``).

Endogenous, not scheduled (honest framing): the daemon's heartbeat is a loop — any daemon's is —
but WHAT it pursues is pressure-derived (recurring abstentions from the failure-receipt ledger), not
a hardcoded target list, and it pursues NOTHING when there is no recurring gap. A single abstention
is remembered but not chased; only recurrence past the floor is.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.graph_scale.triple_store import TripleStore
from packages.knowledge_acquisition import acquire
from packages.knowledge_acquisition.evidence import EvidenceSource

from .gap_signals import MIN_PRESSURE, GapLedger
from .promotion_queue import AcquisitionQueue
from .structural_gaps import StructuralGapScanner

_STORE_FILES = ("terms.txt", "s.col", "p.col", "o.col", "src.col", "meta.json")


@dataclass
class CycleReport:
    cycle: int
    observed: int = 0                    # questions seen this cycle
    new_gaps: int = 0                    # genuinely-abstaining (verified) gaps recorded
    under_pressure: int = 0             # gaps in the pressured target list this cycle (both sources)
    pursued: int = 0                    # gaps run through the acquisition loop this cycle
    pursued_recurrence: int = 0        # of those, pursued because a demand recurred
    pursued_curiosity: int = 0         # of those, pursued from a structural hole (never re-asked)
    verified_queued: int = 0           # consensus-verified facts newly queued
    insufficient_consensus: int = 0    # pursued but stayed abstained (fabrication-0)
    detail: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OvernightReport:
    cycles: int
    gaps_observed: int                  # distinct gaps recorded over the run (recurrence source)
    gaps_under_pressure: int            # distinct gaps in the pressured list (both sources)
    pursued: int                        # distinct gaps run through the loop
    verified_queued: int                # candidate facts in the queue after the run
    insufficient_consensus: int         # pursued gaps that yielded no consensus (stayed honest gaps)
    per_cycle: list[CycleReport]
    curiosity_holes_detected: int = 0   # structural holes the scanner found in the shipped graph
    pursued_recurrence: int = 0         # distinct gaps pursued because a demand recurred
    pursued_curiosity: int = 0          # distinct gaps pursued from a structural hole (self-winding)

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["per_cycle"] = [c.__dict__ for c in self.per_cycle]
        return d


def store_digest(root: Path | str) -> dict[str, Any]:
    """A content fingerprint of a triple store: per-file sha256 over every file in the root (the
    columns, term dict, meta, and any sidecar), plus the row count. Used to PROVE the shipped store
    is byte-unchanged after a daemon run."""
    import hashlib

    root = Path(root)
    files: dict[str, str] = {}
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files[str(p.relative_to(root)).replace("\\", "/")] = \
                    hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        rows = len(TripleStore(root))
    except Exception:
        rows = -1
    return {"files": files, "rows": rows}


class AcquisitionDaemon:
    """Wires gap-detect -> loop -> operator-queue. Writes only to ``scratch_root`` (ephemeral) and
    the ``queue`` / ``ledger`` files it is given; the shipped store is read-only."""

    def __init__(self, *, shipped_root: Path | str, scratch_root: Path | str,
                 evidence: EvidenceSource, queue: AcquisitionQueue, ledger: GapLedger,
                 min_pressure: int = MIN_PRESSURE, enable_curiosity: bool = True,
                 curiosity_kwargs: dict[str, Any] | None = None, property_table: Any = None,
                 log: Callable[..., None] = lambda *a, **k: None):
        self.shipped_root = Path(shipped_root)
        self.scratch_root = Path(scratch_root)
        if self.scratch_root.resolve() == self.shipped_root.resolve():
            raise ValueError("scratch_root must differ from shipped_root — the daemon never writes "
                             "the shipped store")
        self.evidence = evidence
        self.queue = queue
        self.ledger = ledger
        self.min_pressure = min_pressure
        self.enable_curiosity = bool(enable_curiosity)
        # Precomputed sightings, handed straight to `acquire` so they meet the mined ones inside the
        # SAME ConsensusTally under the SAME floor. The daemon does not interpret it; it only carries
        # it, because the join belongs at the consensus layer and not here.
        self.property_table = property_table
        self.curiosity_kwargs = dict(curiosity_kwargs or {})
        self.log = log
        self._handled: set[str] = set()      # gap_keys already pursued this run (no re-mining)
        self._pursued_sources: dict[str, list[str]] = {}   # gap_key -> pressure sources at pursue time
        self._shipped: TripleStore | None = None
        self._holes: list[dict[str, Any]] | None = None    # cached structural-curiosity targets

    # ---- scratch = a working COPY of the graph (so acquire abstains exactly as shipped does,
    #      mines, injects, and re-answers — all WITHOUT touching the shipped store) -------------
    def _init_scratch(self) -> None:
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        # copy only if the scratch store is empty, so a run is reproducible and the shipped store is
        # read once, before any read-handle/memmap is opened on it.
        if not (self.scratch_root / "s.col").exists():
            for name in _STORE_FILES:
                src = self.shipped_root / name
                if src.exists():
                    shutil.copy2(src, self.scratch_root / name)

    def _shipped_store(self) -> TripleStore:
        if self._shipped is None:
            self._shipped = TripleStore(self.shipped_root)
        return self._shipped

    # ---- intrinsic curiosity: the SECOND endogenous source (structural graph holes) -----------
    def curiosity_targets(self) -> list[dict[str, Any]]:
        """Scan the SHIPPED graph (READ-ONLY) for genuinely-valuable structural holes and return
        them as ``pressured``-ready targets. Cached — the shipped store is byte-unchanged across a
        run, so the induced holes do not move; already-pursued keys are filtered by ``tick``. Empty
        (and inert) when curiosity is disabled or the graph induces no schema (no holes)."""
        if not self.enable_curiosity:
            return []
        if self._holes is None:
            try:
                scanner = StructuralGapScanner(self._shipped_store(), **self.curiosity_kwargs)
                self._holes = scanner.targets()
            except Exception as exc:  # curiosity must never crash the daemon
                self.log(f"  [curiosity] scan failed: {exc}")
                self._holes = []
        return self._holes

    # ---- observation: scan a batch of asked questions, record REAL abstentions as pressure -----
    def observe(self, questions: list[str], *, source: str = "daemon") -> int:
        store = self._shipped_store()
        recorded = 0
        for q in questions:
            out = self.ledger.observe(q, store=store, source=source)
            if out.get("gap"):
                recorded += 1
        return recorded

    # ---- one heartbeat: select pressured gaps, pursue the un-handled ones, queue the verified ---
    def tick(self, cycle: int = 0) -> CycleReport:
        rep = CycleReport(cycle=cycle)
        # TWO endogenous sources merged inside pressured(): recurrence (demand) + structural holes
        # (curiosity). Curiosity chooses WHAT; the loop's consensus + operator gate still verify.
        targets = self.ledger.pressured(self.min_pressure,
                                        structural_holes=self.curiosity_targets())
        rep.under_pressure = len(targets)
        for t in targets:
            gk = t["gap_key"]
            if gk in self._handled:
                continue
            self._handled.add(gk)
            sources = t.get("pressure_sources") or []
            self._pursued_sources[gk] = list(sources)
            rep.pursued += 1
            # a gap is "curiosity-driven" when it entered ONLY through the structural-hole source
            # (no one re-asked it) — that is the self-winding signal, distinct from recurrence.
            if "recurrence" in sources or "failure_receipt_seek" in sources:
                rep.pursued_recurrence += 1
            elif "structural_curiosity" in sources:
                rep.pursued_curiosity += 1
            # run the EXISTING closed loop against the SCRATCH copy (never the shipped store)
            r = acquire(t["question"], self.evidence, self.scratch_root,
                        property_table=self.property_table, log=self.log)
            entry = {"gap_key": gk, "question": t["question"], "status": r.status,
                     "pressure_sources": sources,
                     # WHICH TIER ANSWERED is the number the cascade exists to produce: a run where
                     # the web tier is never reached is a run that can keep going unattended.
                     "tiers_run": r.tiers_run, "settled_by": r.settled_by,
                     "domains": r.domains, "object": r.object}
            if r.status in ("acquired", "injected") and (r.domains and len(r.domains) >= 2):
                qid = self.queue.add_result(r)
                entry["queued_item"] = qid
                if qid:
                    rep.verified_queued += 1
            elif r.status == "abstained_insufficient_consensus":
                rep.insufficient_consensus += 1
                # keep the pressure honest: a pursued-but-unverified gap stays a gap (no fabrication)
            rep.detail.append(entry)
        return rep

    # ---- the overnight run: over N cycles, observe accruing questions then pursue pressure -----
    def run_overnight(self, batches: list[list[str]], *, cycles: int | None = None,
                      source: str = "daemon") -> OvernightReport:
        """``batches`` = the questions asked in each time window (cycle). Over cycles, abstentions
        accrue in the ledger; a gap that RECURS crosses the pressure floor and gets pursued, a
        one-off gap never does. Returns the measured gap -> verified-candidate throughput."""
        self._init_scratch()
        n_cycles = cycles if cycles is not None else len(batches)
        per_cycle: list[CycleReport] = []
        for c in range(n_cycles):
            batch = batches[c] if c < len(batches) else []
            observed = self.observe(batch, source=source) if batch else 0
            rep = self.tick(cycle=c)
            rep.observed = len(batch)
            rep.new_gaps = observed
            per_cycle.append(rep)

        all_gaps = self.ledger.all_gaps()
        holes = self.curiosity_targets()
        under_pressure = len(self.ledger.pressured(self.min_pressure, structural_holes=holes))
        pursued_curiosity = sum(1 for gk, srcs in self._pursued_sources.items()
                                if "structural_curiosity" in srcs
                                and "recurrence" not in srcs and "failure_receipt_seek" not in srcs)
        pursued_recurrence = len(self._handled) - pursued_curiosity
        return OvernightReport(
            cycles=n_cycles,
            gaps_observed=len(all_gaps),
            gaps_under_pressure=under_pressure,
            pursued=len(self._handled),
            verified_queued=len(self.queue.items()),
            insufficient_consensus=sum(c.insufficient_consensus for c in per_cycle),
            per_cycle=per_cycle,
            curiosity_holes_detected=len(holes),
            pursued_recurrence=pursued_recurrence,
            pursued_curiosity=pursued_curiosity,
        )
