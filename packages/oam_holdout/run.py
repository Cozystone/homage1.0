# -*- coding: utf-8 -*-
"""OAM — the CONTROLLED overnight run (docs/ATANOR_final_fusion_design.md §4 F3/F-FINAL, §5).

Drives the fusion loop (F1 ``FusionLoop``) the F3 way — scheduler-free (state-pressure ignition at
input=0), INSIDE F5's real enforcing ``AutonomyEnvelope`` (whitelist=read/graph_inject/invent,
killswitch armed, hash-chained audit ledger, shipped-graph promotions queued for one operator
signature) — but PARAMETERISED by the examiner's blind ``Assignment`` so a SPREAD of unseen X is
actually exercised (F3's own ``run_unsupervised`` hardcodes one fixture; this injects the study
materials while keeping the rubric unreachable).

CONTROLLED, not live: bounded N cycles, foreground, FixtureEvidence (offline — no live web), no
scheduler, no daemon, no background process. Each cycle is a FRESH self-winding episode (fresh
``SelfState`` + fresh scratch store + fresh H4 basis), mirroring F3 — which is exactly why the
PERSISTENT holdout (a skill that must compound ACROSS sessions) cannot chain here: that is the
honest frontier, measured, not hidden.

The run entry point ``run_capability`` takes an ``Assignment`` — never a ``Rubric``. That signature
IS the blindness guarantee (see ``examiner.blindness_report``): the acquisition path cannot reach
the answer key or the grading predicates.

The real live overnight OAM run on the actual machine is a SEPARATE, human-gated step (operator
explicit go + this verified envelope). This module starts NO live daemon/scheduler/web.

No-LLM, deterministic given seeds. Writes only under ``scratch_dir``. Imports fusion_loop +
autonomy_envelope + the organs READ-ONLY (edits nothing).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.autonomy_envelope import AutonomyEnvelope
from packages.fusion_loop.envelope_adapter import EnvelopeAdapter
from packages.fusion_loop.loop import FusionLoop, WorldGap
from packages.knowledge_acquisition import FixtureEvidence, acquire
from packages.graph_scale.triple_store import TripleStore

from .examiner import Assignment, Faculty


def _noop(*_a: Any, **_k: Any) -> None:
    return None


# ── per-cycle + per-capability artifacts (all the grader reads) ─────────────────────────────────
@dataclass
class CycleArtifacts:
    """Everything a single controlled cycle produced that the blind grader inspects. Read off the
    loop's honest ``CycleTrace`` — no capability is 'learned' here unless the membrane certified it."""
    index: int
    wall_name: str
    self_wound: bool
    closed: bool
    fabrications: int
    moral_0th_intact: bool
    # acquisition branch
    acquire_status: str = ""
    acquire_object: str = ""
    acquire_answer: str = ""
    acquire_domains: tuple[str, ...] = ()
    fact_certified: bool = False
    # invention branch
    wall_crossed: bool = False
    wall_is_wall: bool = False
    wall_via: str = ""
    wall_verify_execs: int = 0
    wall_invented_new: bool = False
    scheme_certified: bool = False
    # enshrinements / quarantines (kind, label, certified)
    enshrined: tuple[tuple[str, str, bool], ...] = ()
    quarantined: tuple[tuple[str, str], ...] = ()
    # capability reach snapshot
    capability_before: dict[str, Any] = field(default_factory=dict)
    capability_after: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityRunResult:
    """The post-run capability state the examiner grades. Carries the honest run artifacts + the
    controlled-run posture facts (envelope-enforced, killswitch armed, scheduler-free, bounded)."""
    capability_id: str
    faculty: Faculty
    cycles: list[CycleArtifacts]
    # controlled-run posture
    envelope_enforced: bool
    killswitch_armed: bool
    scheduler_free: bool
    bounded_n: int
    no_live_web: bool
    # envelope audit over this capability's run
    audit_records: int
    audit_chain_ok: bool
    pending_promotions: int
    # cross-session fact (PERSISTENT): did a later cycle inherit an earlier cycle's invented basis?
    cross_session_carryover: bool = False
    # totals
    total_fabrications: int = 0

    def any_enshrined(self, kind: str) -> list[tuple[str, str, bool]]:
        out: list[tuple[str, str, bool]] = []
        for c in self.cycles:
            out.extend([e for e in c.enshrined if e[0] == kind])
        return out

    def voiced_or_enshrined_text(self) -> str:
        """All text the loop committed to (enshrined labels + acquire answers) — scanned for
        fabrication traps by the grader."""
        parts: list[str] = []
        for c in self.cycles:
            parts.append(c.acquire_answer)
            parts.append(c.acquire_object)
            parts.extend(lbl for (_k, lbl, _c) in c.enshrined)
        return " ".join(p for p in parts if p)


# ── the fresh scratch store the loop uses (abstains before acquisition) ──────────────────────────
def _seed_abstaining_store(root: Path, entity: str, kind: str) -> None:
    if entity and kind and not (root / "s.col").exists():
        st = TripleStore(root)
        st.add(entity, "is_a", kind)
        st.flush()
        del st


def pre_run_abstains(assignment: Assignment, scratch_dir: Path | str) -> bool:
    """Blindness probe: does a FRESH scratch store (only ``entity is_a kind``) HONESTLY ABSTAIN on
    the graded question BEFORE any acquisition? If yes, a correct post-run answer is genuine
    overnight acquisition, not a pre-seeded lookup. (Acquire family only; invention has no store.)"""
    if assignment.faculty is Faculty.INVENT or not assignment.question:
        return True
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    root = scratch / f"preprobe_{assignment.entity.lower()}"
    _seed_abstaining_store(root, assignment.entity, assignment.kind)
    res = acquire(assignment.question, FixtureEvidence(corpus=[]), root)
    return res.status in ("abstained_insufficient_consensus", "not_relational")


# ── read a CycleTrace into flat artifacts ────────────────────────────────────────────────────────
def _stage_detail(trace: Any, name: str) -> dict[str, Any]:
    for s in trace.stages:
        if s.name == name:
            return dict(s.detail or {})
    return {}


def _artifacts_from_trace(trace: Any, index: int, wall_name: str) -> CycleArtifacts:
    acq = _stage_detail(trace, "ACQUIRE")
    inv = _stage_detail(trace, "INVENT")
    mfact = _stage_detail(trace, "MEMBRANE(fact)")
    mscheme = _stage_detail(trace, "MEMBRANE(scheme)")
    return CycleArtifacts(
        index=index, wall_name=wall_name,
        self_wound=bool(trace.self_wound), closed=bool(trace.closed()),
        fabrications=int(trace.fabrications), moral_0th_intact=bool(trace.moral_0th_intact),
        acquire_status=str(acq.get("status", "")), acquire_object=str(acq.get("object", "")),
        acquire_answer=str(acq.get("answer", "")),
        acquire_domains=tuple(acq.get("domains") or ()),
        fact_certified=bool(mfact.get("certified", False)),
        wall_crossed=bool(inv.get("crossed", False)), wall_is_wall=bool(inv.get("is_wall", False)),
        wall_via=str(inv.get("via", "")), wall_verify_execs=int(inv.get("verify_execs", 0)),
        wall_invented_new=bool(inv.get("invented_new_template", False)),
        scheme_certified=bool(mscheme.get("certified", False)),
        enshrined=tuple((e.kind, e.label, bool(e.membrane_certified and e.moral_ok))
                        for e in trace.enshrined),
        quarantined=tuple((q.kind, q.reason) for q in trace.quarantined),
        capability_before=dict(trace.capability_before), capability_after=dict(trace.capability_after),
    )


# ── run one capability CONTROLLED under an enforcing envelope ────────────────────────────────────
def run_capability(assignment: Assignment, *, scratch_dir: Path | str,
                   envelope: AutonomyEnvelope | None = None,
                   log: Callable[..., None] = _noop) -> CapabilityRunResult:
    """Drive the fusion loop for this ONE blind ``assignment`` under F5's enforcing envelope,
    scheduler-free, bounded N, killswitch armed. Returns the post-run artifacts the examiner grades.

    NOTE the signature: this takes an ``Assignment`` — never a ``Rubric``. The loop's acquisition
    path is structurally unable to reach the answer key. CONTROLLED test: no live web, no scheduler,
    no daemon, foreground.
    """
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    own_env = envelope is None
    env = envelope or AutonomyEnvelope(scratch / "envelope", baseline_score=0.0)
    adapter = EnvelopeAdapter(env)

    evidence = FixtureEvidence(corpus=[dict(d) for d in assignment.corpus])
    world_gap = WorldGap(assignment.entity or "France", assignment.kind or "Country",
                         assignment.question or "what is the capital of France?")
    neg_gap = WorldGap(assignment.neg_entity or "Atlantis", assignment.neg_kind or "Country",
                       assignment.neg_question or "what is the capital of Atlantis?")

    # the ordered walls: PERSISTENT crosses a chain across FRESH sessions; others repeat one wall.
    if assignment.faculty is Faculty.PERSISTENT and assignment.stage_walls:
        walls = list(assignment.stage_walls)
    else:
        walls = [assignment.wall_name] * max(1, int(assignment.n_cycles))

    # redirect the flywheel receipt archive to scratch (hermetic; NOT editing the organ)
    import packages.flywheel.failure_receipts as fr
    orig_archive = fr._ARCHIVE
    fr._ARCHIVE = scratch / "failure_receipts.jsonl"

    cycles: list[CycleArtifacts] = []
    basis_sources_seen: set[str] = set()
    carryover = False
    try:
        for i, wall in enumerate(walls):
            # FRESH per cycle (F3 posture): fresh scratch dir -> fresh store, queue, recipe ledger,
            # H4 basis, and a fresh SelfState (input=0 -> genuine state pressure drives ignition).
            with FusionLoop(scratch_dir=scratch / f"cycle_{i}", envelope=adapter, evidence=evidence,
                            world_gap=world_gap, neg_control_gap=neg_gap, wall_name=wall,
                            h4_seed=assignment.h4_seed, log=log) as loop:
                # cross-session carryover check: does THIS fresh cycle START with any invented basis
                # from a PRIOR cycle? (It cannot — each cycle builds a fresh h4_state. We prove it by
                # reading the sources BEFORE run_cycle: a later cycle inherits nothing the earlier one
                # invented, which is exactly why the persistent compounding chain breaks.)
                start_sources = set(loop.h4_state.get("invented_sources", set()))
                if i > 0 and start_sources & basis_sources_seen:
                    carryover = True
                tr = loop.run_cycle()
                basis_sources_seen |= set(loop.h4_state.get("invented_sources", set()))
            cycles.append(_artifacts_from_trace(tr, i, wall))
    finally:
        fr._ARCHIVE = orig_archive

    ch_ok, _bad = env.ledger.verify_chain()
    return CapabilityRunResult(
        capability_id="", faculty=assignment.faculty, cycles=cycles,
        envelope_enforced=True, killswitch_armed=True, scheduler_free=True,
        bounded_n=len(walls), no_live_web=True,
        audit_records=env.ledger.count(), audit_chain_ok=bool(ch_ok),
        pending_promotions=env.promotions.pending_count(),
        cross_session_carryover=carryover,
        total_fabrications=sum(c.fabrications for c in cycles),
    )
