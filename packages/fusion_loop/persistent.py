# -*- coding: utf-8 -*-
"""F4 — the PERSISTENT-MIND runner: the fusion loop carried ACROSS cycles without degenerating.

This closes the OAM **X4 (persistent)** frontier (docs/ATANOR_final_fusion_design.md §4; the
F-FINAL spread in ``packages.oam_holdout.examiner`` — X4's ``named_unlock`` is literally
"persistent-mind (F3 is fresh-per-cycle: the invented basis does not carry over)").

WHY X4 was PARTIAL (the measured gap, not a claim)
--------------------------------------------------
F1 (``.loop.FusionLoop``) closes ONE cycle. F3 (``.unsupervised.run_unsupervised``) and the OAM run
(``packages.oam_holdout.run.run_capability``) run each cycle as a FRESH self-winding episode — a fresh
``SelfState`` + fresh scratch store + **fresh H4 basis**. So the *composed* order-statistic rung
(``third_max``) — which crosses only when ``second_max``'s PROMOTED template already sits in the basis
— has nothing to build on when cycle 1 starts blank. The compounding chain breaks:

    fresh state:  third_max alone -> OE search exhausts (~272k evals) -> NOT crossed.
    persistent :  second_max (invent, OE ~286 evals, PROMOTE) -> third_max via ANALOGY at 0 evals.

The F-FINAL counterfactual (``grading._persistent_chain_would_cross``) PROVED the capability EXISTS in
a persistent state; only cross-session memory was missing. This module supplies exactly that memory.

WHAT PERSISTS (cycle N+1 starts from cycle N's accumulation, NOT a fresh SelfState)
----------------------------------------------------------------------------------
A single ``PersistentFusionMind`` carries, across every cycle:
  * the **invented H4 basis** (``h4_state`` = promoted order-stat auxiliaries + recipe ledger +
    ``invented_sources``) — so a later rung crosses by analogy at ~0 search (the X4 unlock);
  * the **injected scratch facts** — a persistent world ``TripleStore`` the acquisition branch grows;
  * the **operator-approval queue** + the **fusion recipe ledger** (flywheel fuel), accumulating;
  * the **SelfState** (continuity: age, resumptions, narrative) — explicitly NOT fresh per cycle.
Each cycle is still a REAL ``FusionLoop.run_cycle`` (self-wound at input=0, membrane-certified,
envelope-gated); persistence is injected by handing the fresh per-cycle loop the CARRIED organs.

ANTI-DEGENERATION (the second half — self-winding must ADVANCE, not loop)
------------------------------------------------------------------------
A naive persistent loop DEGENERATES: once it knows the identity and France's capital, it re-asks them
forever and never advances. The fix reuses the **intrinsic-curiosity STRUCTURAL-HOLE** gap detector
(``acquisition_daemon.StructuralGapScanner``, task #20): each cycle the frontier is the top-ranked
*unfilled* structural hole in the persistent graph (an entity missing a relation its type-peers have,
scored by the graph's OWN salience·coverage·uncertainty). When the loop grounds a fact, that hole is
FILLED — the scanner no longer returns it — so the pressure moves to the NEXT hole. An answered thread
is retired structurally; a known fact/identity is never a hole, so it cannot re-ignite as a gap. The
frontier sequence STRICTLY PROGRESSES (measured), it does not loop.

HONEST SCOPE
------------
CONTROLLED, not live: bounded N, foreground, offline ``FixtureEvidence`` (no live web), no scheduler,
no daemon. Every side effect passes the envelope hook AND the membrane; nothing is enshrined that the
membrane did not certify (fabrication 0); the moral 0th gate is checked every cycle; shipped-graph
promotions are QUEUED for one operator signature (never auto-applied). Imports the organs READ-ONLY —
edits none of them; writes only under ``scratch_dir``. No-LLM, deterministic given seeds.

Public surface:
  * PersistentFusionMind        — the runner (``run(n_cycles)`` -> PersistentRunResult)
  * PersistentRunResult / PersistentCycleTrace / PersistenceStep / FrontierStep — the honest trace
  * run_persistent_mind(...)    — convenience one-shot
  * DEFAULT_WORLD_SEED / DEFAULT_FRONTIER_CORPUS — a controlled multi-entity curiosity fixture
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.acquisition_daemon import AcquisitionQueue, StructuralGapScanner
from packages.continuous_self.self_state import SelfState
from packages.graph_scale.triple_store import TripleStore
from packages.knowledge_acquisition import FixtureEvidence
from packages.knowledge_acquisition.evidence import EvidenceSource
from packages.self_acceleration import h4

from .envelope import EnvelopeAction, EnvelopeHook, PermissiveEnvelope
from .loop import FusionLoop, WorldGap
from .membrane import Membrane


def _noop(*_a: Any, **_k: Any) -> None:
    return None


# ── the compounding ladder (the same order-statistic spine H4/F2 use) ─────────────────────────────
DEFAULT_LADDER: tuple[str, ...] = ("second_max", "third_max", "fourth_max", "fifth_max")


# ── a controlled multi-entity CURIOSITY fixture (the advancing frontier substrate) ────────────────
# A schema graph of Countries: five PEERS already carry ``capital`` (inducing the schema, coverage
# >= 0.5); four HOLES lack it, with DESCENDING salience (in-edge degree) so the graph's own signal
# ranks them Germany > Spain > Italy > Egypt. Each hole has offline 2-domain evidence, so grounding
# one FILLS it and the scanner advances to the next — a strictly progressing frontier. The naming is
# never hardcoded as a target list: the SCANNER derives the ranking from the graph; change the graph
# and the order follows (proven in acquisition_daemon's sealed structural-curiosity gate).
def _default_world_seed() -> list[tuple[str, str, str]]:
    facts: list[tuple[str, str, str]] = []
    for country, capital in (("France", "Paris"), ("Japan", "Tokyo"), ("Brazil", "Brasilia"),
                             ("Canada", "Ottawa"), ("India", "NewDelhi")):
        facts += [(country, "is_a", "Country"), (country, "capital", capital)]
    # the holes, with in-edges that make their SALIENCE descend (Germany most central .. Egypt least)
    for country, in_degree in (("Germany", 4), ("Spain", 3), ("Italy", 2), ("Egypt", 1)):
        facts.append((country, "is_a", "Country"))
        for k in range(in_degree):
            facts.append((f"ref_{country}_{k}", "located_in", country))
    return facts


DEFAULT_WORLD_SEED: tuple[tuple[str, str, str], ...] = tuple(_default_world_seed())

# 2-domain offline evidence for each frontier hole + a single-domain negative control (Narnia) so the
# per-cycle membrane bite is a real single-domain quarantine, exactly as the F1/F2 fixtures do.
DEFAULT_FRONTIER_CORPUS: tuple[dict[str, str], ...] = (
    {"url": "https://en.wikipedia.org/wiki/Berlin",
     "text": "Berlin is the capital of Germany, its largest city."},
    {"url": "https://www.britannica.com/place/Germany",
     "text": "Germany is a country in Central Europe. The capital of Germany is Berlin."},
    {"url": "https://en.wikipedia.org/wiki/Madrid",
     "text": "Madrid is the capital of Spain and its most populous city."},
    {"url": "https://www.britannica.com/place/Spain",
     "text": "Spain is a country in Southwestern Europe. The capital of Spain is Madrid."},
    {"url": "https://en.wikipedia.org/wiki/Rome",
     "text": "Rome is the capital of Italy, on the river Tiber."},
    {"url": "https://www.britannica.com/place/Italy",
     "text": "Italy is a country in Southern Europe. The capital of Italy is Rome."},
    {"url": "https://en.wikipedia.org/wiki/Cairo",
     "text": "Cairo is the capital of Egypt and its largest city."},
    {"url": "https://www.britannica.com/place/Egypt",
     "text": "Egypt is a country in North Africa. The capital of Egypt is Cairo."},
    # single-domain negative control -> below the 2-domain floor -> quarantined every cycle
    {"url": "https://narnia.fandom.com/wiki/Cair_Paravel",
     "text": "The capital of Narnia is Cair Paravel, the castle of the High King."},
)


# ── per-cycle trace records (honest, decomposed) ──────────────────────────────────────────────────
@dataclass
class PersistenceStep:
    """The INVENTION axis this cycle: which ladder rung was crossed, HOW, and whether it built on a
    basis that PERSISTED from an earlier cycle (the X4 carry)."""
    cycle: int
    wall: str
    crossed: bool
    is_wall: bool
    via: str                                 # "oe" (fresh invention) | "analogy" (persisted-basis reuse)
    synth_evals: int                         # OE search cost (collapses to ~0 once the basis carries)
    verify_execs: int
    scheme_certified: bool
    invented_new_template: bool
    reused_analogy: bool
    basis_size_start: int                    # invented_sources the carried basis held BEFORE this cycle
    basis_size_end: int
    started_from_persisted_basis: bool       # cycle>0 AND the carried basis already held prior inventions


@dataclass
class FrontierStep:
    """The CURIOSITY axis this cycle: which structural hole the self-winding targeted, and whether it
    was NEW (never targeted before) — the anti-degeneration signal."""
    cycle: int
    gap_key: str
    entity: str
    rel_norm: str
    type_label: str
    question: str
    score: float
    salience: int
    was_new_frontier: bool                   # this gap_key had not been answered in a prior cycle
    grounded_object: str                     # the certified object (mirrored into the world graph)
    fact_certified: bool
    hole_filled: bool                        # after grounding, the scanner no longer returns this hole


@dataclass
class PersistentCycleTrace:
    """Everything one persistent cycle produced — the two axes + the sustained safety floor + the raw
    ``FusionLoop`` cycle trace it was read from."""
    cycle: int
    self_wound: bool
    fabrications: int
    moral_0th_intact: bool
    quarantine_bit: bool                     # the membrane bit the negative controls this cycle
    envelope_calls: int
    envelope_all_authorized: bool            # every side effect this cycle passed the envelope hook
    persistence: PersistenceStep
    frontier: FrontierStep
    raw_trace: Any = None                    # the underlying loop.CycleTrace (for the OAM re-run mapping)


# ── the run result + the honest verdict ───────────────────────────────────────────────────────────
@dataclass
class PersistentRunResult:
    cycles: list[PersistentCycleTrace]
    ladder: list[str]
    # cross-cycle facts
    audit_records: int
    audit_chain_ok: bool
    pending_promotions: int
    world_store_root: str

    # ---- (a) the persistence-trace (composed rung crosses BECAUSE an earlier rung persisted) ------
    def composed_via_persistence(self) -> dict[str, Any] | None:
        """The X4 unlock trace: find the FIRST cycle that crossed a composed rung by ANALOGY on a
        basis that PERSISTED from an earlier cycle's fresh (OE) invention. Returns the (base, composed)
        pair + costs, or None if the chain did not compound."""
        # the earliest fresh (OE) invention that PROMOTED a template
        base = next((c for c in self.cycles
                     if c.persistence.crossed and c.persistence.via == "oe"
                     and c.persistence.invented_new_template), None)
        if base is None:
            return None
        # the earliest LATER cycle that crossed by analogy on the carried basis
        comp = next((c for c in self.cycles
                     if c.cycle > base.cycle and c.persistence.crossed
                     and c.persistence.reused_analogy
                     and c.persistence.started_from_persisted_basis), None)
        if comp is None:
            return None
        return {
            "base_cycle": base.cycle, "base_wall": base.persistence.wall,
            "base_via": base.persistence.via, "base_synth_evals": base.persistence.synth_evals,
            "composed_cycle": comp.cycle, "composed_wall": comp.persistence.wall,
            "composed_via": comp.persistence.via, "composed_synth_evals": comp.persistence.synth_evals,
            "composed_scheme_certified": comp.persistence.scheme_certified,
            "basis_carried": comp.persistence.basis_size_start,
        }

    def ladder_reach_curve(self) -> list[int]:
        """Cumulative distinct ladder rungs crossed by cycle — the compounding reach curve."""
        seen: set[str] = set()
        out: list[int] = []
        for c in self.cycles:
            if c.persistence.crossed and c.persistence.is_wall:
                seen.add(c.persistence.wall)
            out.append(len(seen))
        return out

    # ---- (b) the anti-degeneration frontier progression ------------------------------------------
    def frontier_sequence(self) -> list[str]:
        return [c.frontier.gap_key for c in self.cycles]

    def frontier_strictly_progresses(self) -> bool:
        """No gap_key repeats (not looping) AND every cycle targeted a frontier that had NOT been
        answered before (advancing to a NEW structural hole)."""
        seq = self.frontier_sequence()
        no_repeat = len(set(seq)) == len(seq)
        all_new = all(c.frontier.was_new_frontier for c in self.cycles)
        return bool(seq and no_repeat and all_new)

    def answered_never_reasked(self) -> bool:
        """Once a hole is filled, its gap_key never re-appears as a later cycle's frontier."""
        answered: set[str] = set()
        for c in self.cycles:
            if c.frontier.gap_key in answered:
                return False
            if c.frontier.hole_filled:
                answered.add(c.frontier.gap_key)
        return True

    # ---- (c) sustained safety --------------------------------------------------------------------
    def sustained_zero_fabrication(self) -> bool:
        return all(c.fabrications == 0 for c in self.cycles)

    def sustained_moral(self) -> bool:
        return all(c.moral_0th_intact for c in self.cycles)

    def sustained_quarantine(self) -> bool:
        return all(c.quarantine_bit for c in self.cycles)

    def envelope_consulted_every_side_effect(self) -> bool:
        return all(c.envelope_all_authorized and c.envelope_calls > 0 for c in self.cycles)

    def self_wound_every_cycle(self) -> bool:
        return all(c.self_wound for c in self.cycles)

    def total_fabrications(self) -> int:
        return sum(c.fabrications for c in self.cycles)

    def cross_session_carryover(self) -> bool:
        """The OAM field: did a LATER cycle inherit an EARLIER cycle's invented basis? True here by
        construction (that IS the persistent-mind unlock) — computed honestly from the carried basis."""
        return any(c.persistence.started_from_persisted_basis for c in self.cycles[1:])

    # ---- the honest verdict ----------------------------------------------------------------------
    def verdict(self) -> dict[str, Any]:
        pv = self.composed_via_persistence()
        a_ok = pv is not None and pv["composed_scheme_certified"] and pv["composed_synth_evals"] == 0
        b_ok = self.frontier_strictly_progresses() and self.answered_never_reasked()
        c_ok = (self.sustained_zero_fabrication() and self.sustained_moral()
                and self.sustained_quarantine() and self.envelope_consulted_every_side_effect()
                and self.self_wound_every_cycle())
        headline = "PERSISTENT-MIND-SEALED" if (a_ok and b_ok and c_ok) else "INCOMPLETE"
        return {
            "headline": headline,
            "a_composed_crosses_via_persistence": bool(a_ok),
            "b_frontier_advances_no_degeneration": bool(b_ok),
            "c_zero_fab_moral_envelope": bool(c_ok),
            "persistence_trace": pv,
            "ladder_reach_curve": self.ladder_reach_curve(),
            "frontier_sequence": self.frontier_sequence(),
            "frontier_entities": [c.frontier.entity for c in self.cycles],
            "cross_session_carryover": self.cross_session_carryover(),
            "sustained_zero_fabrication": self.sustained_zero_fabrication(),
            "sustained_moral": self.sustained_moral(),
            "sustained_quarantine": self.sustained_quarantine(),
            "envelope_every_side_effect": self.envelope_consulted_every_side_effect(),
            "audit_chain_ok": self.audit_chain_ok,
            "pending_promotions": self.pending_promotions,
            "total_fabrications": self.total_fabrications(),
        }

    def summary(self) -> dict[str, Any]:
        return {"ladder": self.ladder, "n_cycles": len(self.cycles), "verdict": self.verdict(),
                "cycles": [{"cycle": c.cycle, "wall": c.persistence.wall, "via": c.persistence.via,
                            "synth_evals": c.persistence.synth_evals,
                            "frontier": c.frontier.entity, "gap_key": c.frontier.gap_key,
                            "grounded": c.frontier.grounded_object, "new": c.frontier.was_new_frontier,
                            "self_wound": c.self_wound, "fabrications": c.fabrications}
                           for c in self.cycles]}


# ── the runner ────────────────────────────────────────────────────────────────────────────────────
class PersistentFusionMind:
    """A fusion mind whose state CARRIES across cycles (basis + facts + ledger + SelfState) while a
    structural-hole curiosity frontier keeps it ADVANCING. Use as a context manager.

    Each cycle runs a REAL ``FusionLoop.run_cycle`` — but the fresh per-cycle loop is handed the
    CARRIED organs, so cycle N+1 genuinely starts from cycle N's accumulation. Reuses the sealed
    organs verbatim; adds only the persistence wiring + the advancing frontier selection."""

    def __init__(self, *, scratch_dir: Path | str,
                 evidence: EvidenceSource | None = None,
                 membrane: Membrane | None = None,
                 envelope: EnvelopeHook | None = None,
                 world_seed: tuple[tuple[str, str, str], ...] = DEFAULT_WORLD_SEED,
                 ladder: tuple[str, ...] = DEFAULT_LADDER,
                 focus_relation: str = "capital",
                 h4_seed: int = 7,
                 advance_frontier: bool = True,
                 log: Callable[..., None] = _noop):
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.evidence: EvidenceSource = evidence or FixtureEvidence(corpus=[dict(d) for d in DEFAULT_FRONTIER_CORPUS])
        self.membrane: Membrane = membrane or Membrane()
        self.envelope: EnvelopeHook = envelope or PermissiveEnvelope()
        self.ladder = tuple(ladder)
        self.focus_relation = focus_relation
        self.h4_seed = int(h4_seed)
        # advance_frontier=False is the DEGENERATE BASELINE: the mind still carries its basis, but it
        # does NOT integrate answers into its world model and does NOT retire answered threads — so its
        # curiosity re-selects the SAME top hole forever (it re-asks an answered question and gets
        # stuck). advance_frontier=True is the anti-degeneration fix (fill + retire -> the frontier
        # advances). The two differ in ONE variable, isolating the mechanism.
        self.advance_frontier = bool(advance_frontier)
        self.log = log

        # ── the PERSISTENT organs (carried across every cycle) ────────────────────────────────────
        self._h4_state = h4.fresh_state()                      # the invented basis (grows, carries)
        self._self_state = SelfState()                         # continuity — NOT fresh per cycle
        self._queue = AcquisitionQueue(self.scratch_dir / "promotion_queue.json")  # accumulates
        self._recipe_ledger_path = self.scratch_dir / "fusion_recipes.jsonl"       # accumulates
        # the persistent world graph the structural-hole scanner reads (the advancing frontier lives here)
        self._world_root = self.scratch_dir / "world_store"
        self._seed_world(world_seed)

        # frontier bookkeeping (the anti-degeneration state)
        self._answered_gap_keys: list[str] = []
        self._crossed_walls: list[str] = []
        # invention carry bookkeeping (mirrors oam_holdout.run's carryover detection, honestly)
        self._invented_sources_seen: set[str] = set()
        # redirect the flywheel receipt archive under scratch (hermetic; NOT editing the organ)
        import packages.flywheel.failure_receipts as _fr
        self._fr = _fr
        self._fr_orig = _fr._ARCHIVE
        _fr._ARCHIVE = self.scratch_dir / "failure_receipts.jsonl"

    # ---- lifecycle -------------------------------------------------------------------------------
    def close(self) -> None:
        self._fr._ARCHIVE = self._fr_orig

    def __enter__(self) -> "PersistentFusionMind":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- the persistent world graph --------------------------------------------------------------
    def _seed_world(self, seed: tuple[tuple[str, str, str], ...]) -> None:
        st = TripleStore(self._world_root)
        for s, p, o in seed:
            st.add(s, p, o)
        st.flush()
        del st

    def _scan_holes(self) -> list[Any]:
        """Read the persistent graph (READ-ONLY) and rank its structural holes by the graph's OWN
        salience·coverage·uncertainty signal (task #20). Filled holes are absent by construction."""
        return StructuralGapScanner(TripleStore(self._world_root)).scan()

    def _entity_has_relation(self, entity: str, rel_norm: str) -> bool:
        """Does the persistent graph already record ``entity`` -> ``rel_norm`` (the hole is filled)?"""
        for h in self._scan_holes():
            if h.entity == entity and h.rel_norm == rel_norm:
                return False
        return True

    # ---- frontier selection (advancing, retirement-aware) ----------------------------------------
    def _select_frontier(self) -> Any | None:
        """The top-ranked UNANSWERED structural hole in the focus relation. Skips gap_keys already
        answered — so once a hole is filled the pressure targets the NEXT unfilled hole. Returns the
        ``StructuralHole`` or None if the frontier is exhausted."""
        for hole in self._scan_holes():
            if hole.rel_norm != self.focus_relation:
                continue
            # anti-degeneration: skip a thread already answered so the pressure targets a NEW hole.
            # the degenerate baseline (advance_frontier=False) omits this skip AND never fills a hole,
            # so the scanner keeps returning the same top hole and the mind loops.
            if self.advance_frontier and hole.gap_key in self._answered_gap_keys:
                continue
            return hole
        return None

    def _next_wall(self) -> str:
        for w in self.ladder:
            if w not in self._crossed_walls:
                return w
        return self.ladder[-1]

    # ---- mirror a certified fact into the persistent graph (envelope-gated) ----------------------
    def _mirror_certified_fact(self, entity: str, obj: str, cert: dict[str, Any] | None,
                               topic: str) -> bool:
        """Inject the membrane-CERTIFIED acquired fact into the persistent world graph so the hole
        fills and the frontier advances next cycle. Envelope-gated (graph_inject): a real side effect
        the envelope authorizes. Never called on an uncertified fact (fabrication 0)."""
        action = EnvelopeAction(kind="graph_inject", topic=topic,
                                payload={"entity": entity, "relation": self.focus_relation, "object": obj},
                                membrane_certificate=cert)
        if not self.envelope.authorize(action).allowed:
            return False
        st = TripleStore(self._world_root)
        st.add(entity, self.focus_relation, obj)
        st.flush()
        del st
        return True

    # =============================================================================================
    # ONE PERSISTENT CYCLE
    # =============================================================================================
    def run_cycle(self, index: int) -> PersistentCycleTrace:
        hole = self._select_frontier()
        if hole is None:
            raise RuntimeError("frontier exhausted: no unanswered structural hole remains — seed more "
                               "holes for a longer run")
        was_new = hole.gap_key not in self._answered_gap_keys
        world_gap = WorldGap(hole.entity, hole.type_label, hole.question)
        wall = self._next_wall()
        basis_start = len(self._h4_state["invented_sources"])
        started_persisted = bool(index > 0 and self._invented_sources_seen)

        # a FRESH per-cycle FusionLoop (the F3/OAM posture) — but handed the CARRIED organs, so this
        # cycle genuinely starts from the accumulated basis/facts/ledger/SelfState (NOT fresh).
        with FusionLoop(scratch_dir=self.scratch_dir / f"cycle_{index}", envelope=self.envelope,
                        evidence=self.evidence, membrane=self.membrane, self_state=self._self_state,
                        world_gap=world_gap, wall_name=wall, h4_seed=self.h4_seed, log=self.log) as loop:
            loop.h4_state = self._h4_state                    # CARRY the invented basis (the X4 unlock)
            loop.queue = self._queue                          # CARRY the operator-approval queue
            loop.recipe_ledger_path = self._recipe_ledger_path  # CARRY the flywheel recipe ledger
            tr = loop.run_cycle()

        basis_end = len(self._h4_state["invented_sources"])
        self._invented_sources_seen |= set(self._h4_state["invented_sources"])

        # read the two axes off the honest trace ---------------------------------------------------
        inv = _stage_detail(tr, "INVENT")
        mscheme = _stage_detail(tr, "MEMBRANE(scheme)")
        acq = _stage_detail(tr, "ACQUIRE")
        mfact = _stage_detail(tr, "MEMBRANE(fact)")

        crossed = bool(inv.get("crossed", False))
        via = str(inv.get("via", ""))
        scheme_certified = bool(mscheme.get("certified", False))
        if crossed and inv.get("is_wall", True) and wall not in self._crossed_walls:
            self._crossed_walls.append(wall)

        persistence = PersistenceStep(
            cycle=index, wall=wall, crossed=crossed, is_wall=bool(inv.get("is_wall", True)),
            via=via, synth_evals=int(inv.get("synth_evals", 0)),
            verify_execs=int(inv.get("verify_execs", 0)), scheme_certified=scheme_certified,
            invented_new_template=bool(inv.get("invented_new_template", False)),
            reused_analogy=(via == "analogy"), basis_size_start=basis_start, basis_size_end=basis_end,
            started_from_persisted_basis=started_persisted)

        # curiosity frontier: mirror the certified fact into the graph so the hole fills -----------
        # (the degenerate baseline skips this: it never updates its world model -> never retires the
        # thread -> the scanner re-serves the same hole -> the mind loops.)
        fact_certified = bool(mfact.get("certified", False))
        grounded_object = str(acq.get("object", "")) if fact_certified else ""
        hole_filled = False
        if self.advance_frontier and fact_certified and grounded_object:
            mirrored = self._mirror_certified_fact(hole.entity, grounded_object,
                                                   mfact.get("certificate") if isinstance(mfact, dict) else None,
                                                   topic=f"thread:{hole.entity}")
            if mirrored:
                self._answered_gap_keys.append(hole.gap_key)
                hole_filled = self._entity_has_relation(hole.entity, hole.rel_norm)

        frontier = FrontierStep(
            cycle=index, gap_key=hole.gap_key, entity=hole.entity, rel_norm=hole.rel_norm,
            type_label=hole.type_label, question=hole.question, score=float(hole.score),
            salience=int(hole.salience), was_new_frontier=was_new, grounded_object=grounded_object,
            fact_certified=fact_certified, hole_filled=hole_filled)

        # sustained safety floor this cycle --------------------------------------------------------
        neg_consensus_ok = any(s.name == "NEG_CONTROL(consensus)" and s.ok for s in tr.stages)
        neg_signal_ok = any(s.name == "NEG_CONTROL(no-signal)" and s.ok for s in tr.stages)
        env_calls = list(tr.envelope_calls)
        env_all_ok = bool(env_calls) and all(c.get("allowed", False) for c in env_calls)

        return PersistentCycleTrace(
            cycle=index, self_wound=bool(tr.self_wound), fabrications=int(tr.fabrications),
            moral_0th_intact=bool(tr.moral_0th_intact),
            quarantine_bit=bool(neg_consensus_ok and neg_signal_ok),
            envelope_calls=len(env_calls), envelope_all_authorized=env_all_ok,
            persistence=persistence, frontier=frontier, raw_trace=tr)

    # ---- run N cycles ----------------------------------------------------------------------------
    def run(self, n_cycles: int) -> PersistentRunResult:
        cycles = [self.run_cycle(i) for i in range(int(n_cycles))]
        audit_records, audit_chain_ok, pending = self._audit_snapshot()
        return PersistentRunResult(
            cycles=cycles, ladder=list(self.ladder), audit_records=audit_records,
            audit_chain_ok=audit_chain_ok, pending_promotions=pending,
            world_store_root=str(self._world_root))

    def _audit_snapshot(self) -> tuple[int, bool, int]:
        """If the envelope is F5's enforcing ``AutonomyEnvelope`` (via ``EnvelopeAdapter``), read its
        hash-chained audit ledger + pending-promotion count; otherwise (permissive) report the queue
        depth and a trivially-intact chain (nothing hits a shipped store either way)."""
        inner = getattr(self.envelope, "inner", None)
        ledger = getattr(inner, "ledger", None)
        promos = getattr(inner, "promotions", None)
        queue_pending = len(self._queue.pending())
        if ledger is not None:
            chain_ok, _bad = ledger.verify_chain()
            pending = promos.pending_count() if promos is not None else queue_pending
            return int(ledger.count()), bool(chain_ok), int(pending)
        return queue_pending, True, queue_pending


# ── trace helper (same shape oam_holdout.run reads) ───────────────────────────────────────────────
def _stage_detail(trace: Any, name: str) -> dict[str, Any]:
    for s in trace.stages:
        if s.name == name:
            return dict(s.detail or {})
    return {}


# ── convenience one-shot ──────────────────────────────────────────────────────────────────────────
def run_persistent_mind(*, scratch_dir: Path | str, n_cycles: int = 4,
                        evidence: EvidenceSource | None = None,
                        envelope: EnvelopeHook | None = None,
                        world_seed: tuple[tuple[str, str, str], ...] = DEFAULT_WORLD_SEED,
                        ladder: tuple[str, ...] = DEFAULT_LADDER,
                        focus_relation: str = "capital", h4_seed: int = 7,
                        advance_frontier: bool = True,
                        log: Callable[..., None] = _noop) -> PersistentRunResult:
    """Run the persistent-mind runner for ``n_cycles`` and return the honest result. CONTROLLED test:
    offline evidence, no scheduler, no daemon, foreground. ``advance_frontier=False`` is the
    degenerate baseline (re-asks the same answered thread)."""
    with PersistentFusionMind(scratch_dir=scratch_dir, evidence=evidence, envelope=envelope,
                              world_seed=world_seed, ladder=ladder, focus_relation=focus_relation,
                              h4_seed=h4_seed, advance_frontier=advance_frontier, log=log) as mind:
        return mind.run(n_cycles)
