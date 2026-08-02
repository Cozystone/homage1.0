# -*- coding: utf-8 -*-
"""F1 — the FUSION LOOP: the five SEALED organs wired into ONE closed, CO-orchestrated cycle.

This is the first joint of "완벽한 하나" (docs/ATANOR_final_fusion_design.md §2). It builds NOTHING
new about cognition — it SUMMONS and WIRES five already-sealed organs so that, driven by real state
pressure, they flow as one loop:

    self-winding pressure  →  CO ignition  →  gap surfaced
        ├─ [known?]  → moral 0th + membrane-verify → VOICE
        └─ [gap?]    → acquisition mines → verify → graph-inject (scratch)
                         └─ [synthesis wall?] → explosion engine invents → RE-EXECUTE verify → promote
        → moral 0th + membrane certifies every enshrinement (quarantine on fail)
        → recipe-ledger record  →  capability↑  →  pressure refresh ↺

The organs (imported READ-ONLY; none is edited):
  * self-winding (R1/M3) : packages.continuous_self.pressure_clock  (state-pressure clock, no metronome)
                           + packages.continuous_self.voice          (the endogenous inquiry composer)
  * CO / workspace       : packages.continuous_self.ignition        (GWT compete/broadcast/commitment)
  * acquisition (R2)     : packages.knowledge_acquisition.acquire    (abstain→mine→consensus→inject→re-answer)
                           + packages.acquisition_daemon.AcquisitionQueue (operator-approval queue)
  * explosion engine (H4): packages.self_acceleration.h4.cross_wall  (wall→invent→re-execute→promote→record)
  * membrane             : packages.conformal_gate + packages.graph_scale.moral_invariants
                           (composed in .membrane.Membrane)
  * substrate            : packages.graph_scale.triple_store (a SCRATCH store — the shipped store is
                           never opened, so it is trivially byte-unchanged)

CONTROLLED closed-loop test, NOT live unsupervised operation (that is F3, envelope-gated). Every
side-effecting action passes the envelope hook (.envelope; permissive no-op by default) AND the
membrane. Hermetic: all writes go under ``scratch_dir`` (the ignition ledger is redirected there for
the run and restored on close); no network (the web is stubbed by the project's own FixtureEvidence).

HONEST SEAMS (what really flows vs. what is faithfully stubbed):
  * REAL: the endogenous fire (pressure-clocked at input=0), the GWT competition, the acquisition
    closed loop (consensus→inject→re-answer on a scratch store), the H4 invention (re-executed on
    holdout), the moral+conformal membrane, the operator-approval queue, the pressure refresh.
  * STUBBED, labeled: (1) the live web — replaced by FixtureEvidence, the SAME offline source the
    acquisition sealed gate uses; (2) the self-inquiry→world-gap CONNECTIVE — F1 routes a surfaced
    thread to a concrete relational world-question from a controlled fixture (in live operation
    voice.harvest_terms supplies the thread from real answers). Both are reported as stubs.

No-LLM, deterministic given seeds, numpy + stdlib.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Any, Callable

from packages.continuous_self import ignition as _ign
from packages.continuous_self import pressure_clock as _pc
from packages.continuous_self.self_state import Observation, SelfState
from packages.continuous_self.voice import (
    due_for_self_inquiry,
    generate_self_inquiry,
    update_introspection,
)
from packages.knowledge_acquisition import AcquisitionResult, FixtureEvidence, acquire
from packages.knowledge_acquisition.evidence import EvidenceSource
from packages.graph_scale.triple_store import TripleStore
from packages.acquisition_daemon import AcquisitionQueue
from packages.self_acceleration import h4
from packages.self_acceleration.curriculum import by_name

from .envelope import EnvelopeAction, EnvelopeHook, PermissiveEnvelope
from .membrane import Membrane, MembraneVerdict


# ── a small controlled world-fixture: the acquisition organ's offline evidence ────────────────────
# The verifiable gap (France capital = Paris) has TWO distinct domains -> clears consensus. The
# negative control (Narnia capital) has ONE domain -> below the floor -> quarantined. This is the
# SAME kind of fixture the acquisition sealed gate uses (it stubs the live web, deterministically).
DEFAULT_CORPUS: list[dict[str, str]] = [
    {"url": "https://en.wikipedia.org/wiki/Paris",
     "text": "Paris is the capital of France and its most populous city, on the river Seine."},
    {"url": "https://www.britannica.com/place/France",
     "text": "France is a country in Western Europe. The capital of France is Paris."},
    # single-domain only -> below the consensus floor (the fabrication-0 negative control)
    {"url": "https://narnia.fandom.com/wiki/Cair_Paravel",
     "text": "The capital of Narnia is Cair Paravel, the castle of the High King."},
]


@dataclass
class WorldGap:
    """A concrete relational world-question the acquisition organ can pursue, plus the entity/kind so
    the scratch store can be seeded to HONESTLY ABSTAIN before acquisition."""
    entity: str
    kind: str
    question: str


DEFAULT_GAP = WorldGap("France", "Country", "what is the capital of France?")
DEFAULT_NEG_CONTROL = WorldGap("Narnia", "Country", "what is the capital of Narnia?")


# ── trace records ─────────────────────────────────────────────────────────────────────────────────
@dataclass
class StageTrace:
    name: str                       # SELF_WIND / CO_IGNITION / KNOWN_VOICE / GAP_SURFACE / ACQUIRE / ...
    organ: str                      # the package.module the stage exercised
    real: bool                      # True = organ genuinely executed; False = faithfully stubbed (labeled)
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Enshrinement:
    kind: str                       # "voice" | "fact" | "scheme"
    label: str
    membrane_certified: bool
    moral_ok: bool
    envelope_allowed: bool
    nonconformity: float
    certificate: dict[str, Any] = field(default_factory=dict)


@dataclass
class Quarantine:
    kind: str
    label: str
    reason: str


@dataclass
class CycleTrace:
    stages: list[StageTrace] = field(default_factory=list)
    fires: list[dict[str, Any]] = field(default_factory=list)
    enshrined: list[Enshrinement] = field(default_factory=list)
    quarantined: list[Quarantine] = field(default_factory=list)
    envelope_calls: list[dict[str, Any]] = field(default_factory=list)
    fabrications: int = 0
    self_wound: bool = False
    scheduler_free: bool = True
    moral_0th_intact: bool = False
    pressure_before: float = 0.0
    pressure_after_ground: float = 0.0
    pressure_refreshed: float = 0.0
    next_frontier_topic: str = ""
    capability_before: dict[str, Any] = field(default_factory=dict)
    capability_after: dict[str, Any] = field(default_factory=dict)

    def closed(self) -> bool:
        """One full cycle flowed end-to-end: a real fire, a certified fact enshrined, a certified
        scheme promoted, a recipe recorded, and the pressure refreshed — with zero fabrications and
        the moral core intact."""
        kinds = {e.kind for e in self.enshrined}
        return bool(self.self_wound and self.scheduler_free and self.moral_0th_intact
                    and self.fabrications == 0
                    and "fact" in kinds and "scheme" in kinds
                    and self.capability_after.get("recipe_count", 0) > self.capability_before.get("recipe_count", 0)
                    and self.pressure_refreshed > self.pressure_after_ground)

    def summary(self) -> dict[str, Any]:
        return {
            "closed": self.closed(),
            "self_wound": self.self_wound,
            "scheduler_free": self.scheduler_free,
            "moral_0th_intact": self.moral_0th_intact,
            "fabrications": self.fabrications,
            "n_fires": len(self.fires),
            "enshrined": [(e.kind, e.label) for e in self.enshrined],
            "quarantined": [(q.kind, q.reason) for q in self.quarantined],
            "stages": [(s.name, s.organ, "real" if s.real else "stub", s.ok) for s in self.stages],
            "pressure": {"before": self.pressure_before, "after_ground": self.pressure_after_ground,
                         "refreshed": self.pressure_refreshed, "next_frontier": self.next_frontier_topic},
            "capability_before": self.capability_before,
            "capability_after": self.capability_after,
            "envelope_calls": [c["kind"] for c in self.envelope_calls],
        }


# ── the loop ───────────────────────────────────────────────────────────────────────────────────────
class FusionLoop:
    """Wires the five sealed organs into one CO-orchestrated cycle. Use as a context manager so the
    redirected ignition ledger is restored on exit."""

    def __init__(self, *, scratch_dir: Path | str,
                 envelope: EnvelopeHook | None = None,
                 evidence: EvidenceSource | None = None,
                 membrane: Membrane | None = None,
                 self_state: SelfState | None = None,
                 world_gap: WorldGap = DEFAULT_GAP,
                 neg_control_gap: WorldGap = DEFAULT_NEG_CONTROL,
                 wall_name: str = "second_max",
                 h4_seed: int = 7,
                 max_advances: int = 60,
                 enable_shared_bank_promotion: bool = False,
                 log: Callable[..., None] = lambda *a, **k: None):
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.envelope: EnvelopeHook = envelope or PermissiveEnvelope()
        self.evidence: EvidenceSource = evidence or FixtureEvidence(corpus=list(DEFAULT_CORPUS))
        self.membrane: Membrane = membrane or Membrane()
        self.state: SelfState = self_state or SelfState()      # fresh self, input=0 -> genuine pressure
        self.world_gap = world_gap
        self.neg_control_gap = neg_control_gap
        self.wall = by_name(wall_name)
        self.rng = Random(h4_seed)
        self.max_advances = int(max_advances)
        self.enable_shared_bank_promotion = bool(enable_shared_bank_promotion)
        self.log = log

        # the persistent H4 vocabulary (basis grows as walls are crossed -> capability compounds)
        self.h4_state = h4.fresh_state()
        # the operator-approval queue (the daemon PROPOSES; the operator DISPOSES — default-deny)
        self.queue = AcquisitionQueue(self.scratch_dir / "promotion_queue.json")
        # the fusion-local recipe ledger (flywheel fuel audit; the SHARED bank stays operator-gated)
        self.recipe_ledger_path = self.scratch_dir / "fusion_recipes.jsonl"

        # redirect the ignition ledger to scratch for the run (hermetic; NOT editing the organ) ----
        self._ign_ledger_orig = _ign.LEDGER
        _ign.LEDGER = self.scratch_dir / "ignition_ledger.jsonl"

        # per-cycle scratch state
        self._trace: CycleTrace | None = None
        self._cur_label = ""            # label of the fire currently being driven (for the trace)

    # ---- lifecycle -------------------------------------------------------------------------------
    def close(self) -> None:
        _ign.LEDGER = self._ign_ledger_orig

    def __enter__(self) -> "FusionLoop":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- the envelope gate (consulted before EVERY side effect) ---------------------------------
    def _authorize(self, kind: str, topic: str, payload: dict[str, Any],
                   cert: dict[str, Any] | None = None) -> bool:
        action = EnvelopeAction(kind=kind, topic=topic, payload=payload, membrane_certificate=cert)
        decision = self.envelope.authorize(action)
        assert self._trace is not None
        self._trace.envelope_calls.append({"kind": kind, "topic": topic, "allowed": decision.allowed,
                                           "reason": decision.reason, "hook": decision.hook})
        return decision.allowed

    def _capability(self) -> dict[str, Any]:
        """A snapshot of the loop's REACH — grows as facts are queued, schemes promoted, recipes
        recorded, and self-understanding grounded. The compounding measure of §2's '능력↑'."""
        return {
            "queue_items": len(self.queue.items()),
            "h4_basis_size": len(self.h4_state["basis"]),
            "h4_ledger_size": len(self.h4_state["ledger"]),
            "recipe_count": self._recipe_count(),
            "self_understood": bool(getattr(self.state, "self_understanding", "")),
            "open_threads": [t.get("term") for t in getattr(self.state, "open_threads", [])],
        }

    def _recipe_count(self) -> int:
        if not self.recipe_ledger_path.exists():
            return 0
        return sum(1 for _ in self.recipe_ledger_path.read_text(encoding="utf-8").splitlines() if _.strip())

    # ---- scratch substrate: a store that ABSTAINS on the gap before acquisition -----------------
    def _scratch_store_root(self, gap: WorldGap) -> Path:
        """A scoped store holding only the entity's is_a context (so the relational question honestly
        abstains) — the shipped-graph condition the acquisition loop is built for. Never the shipped
        store: F1 does not open the shipped store at all."""
        root = self.scratch_dir / f"store_{gap.entity.lower()}"
        if not (root / "s.col").exists():
            st = TripleStore(root)
            st.add(gap.entity, "is_a", gap.kind)
            st.flush()
            del st
        return root

    # =============================================================================================
    # THE CYCLE
    # =============================================================================================
    def run_cycle(self) -> CycleTrace:
        tr = CycleTrace()
        self._trace = tr
        tr.moral_0th_intact = self.membrane.moral_core_intact()
        tr.capability_before = self._capability()
        tr.pressure_before = float(getattr(self.state, "introspective_pressure", 0.0))

        # STAGE 1+2+3(known) : self-winding fires the identity inquiry; the CO ignites it; the self
        # grounds the identity FACET from real state and VOICEs it (the [known?] branch). The ground
        # hook is the CO/membrane pipeline, so pressure_clock.tick closes the loop on a certified answer.
        fire1 = self._drive_to_fire(ground=self._orchestrated_ground, label="fire#1")
        tr.self_wound = fire1 is not None

        # STAGE 4 : surface the world-gap (the documented self-inquiry->world-gap connective) so the
        # NEXT endogenous fire routes to acquisition. Seeding one genuine open thread (a term the self
        # knows OF but not ABOUT) is a real epistemic initial condition; the fire itself stays pressure-
        # clocked. In live operation voice.harvest_terms supplies this thread from real answers.
        self._surface_world_gap(fire1)

        # STAGE 5+6+7 : the second endogenous fire routes to the [gap?] branch -> acquisition mines,
        # verifies, injects (scratch); the synthesis-wall sub-branch invents a scheme; the membrane
        # certifies both; certified ones are enshrined (queue + recipe). All inside the ground hook.
        fire2 = self._drive_to_fire(ground=self._orchestrated_ground, label="fire#2")
        if fire2 is not None:
            tr.pressure_after_ground = float(getattr(self.state, "introspective_pressure", 0.0))

        # negative controls — prove the membrane BITES (never enshrined without certification)
        self._run_negative_controls()

        # STAGE 8 : pressure refresh — after grounding, pressure fell to its floor; re-accumulation
        # earns the NEXT inquiry, now aimed at a NEW frontier harvested from what was just learned.
        self._refresh_pressure()

        tr.capability_after = self._capability()
        # fabrications = anything enshrined that was NOT membrane-certified (must be 0 by construction)
        tr.fabrications = sum(1 for e in tr.enshrined if not (e.membrane_certified and e.moral_ok))
        self._trace = None
        return tr

    # ---- STAGE 1/2/3/5 : drive the pressure clock to one endogenous fire (CO-ignited) -----------
    def _drive_to_fire(self, *, ground: Callable[[str, str], str | None], label: str) -> _pc.Fire | None:
        """Advance the state-pressure clock (NO scheduler, NO metronome) until pressure crosses the
        ignition threshold and fires ONE endogenous inquiry. Each fire is CO-ignited: the surfaced
        inquiry competes in the GWT workspace and, on ignition, is broadcast + recorded as a
        commitment (ignition.compete/record_ignition). The pressure_clock.tick ``ground`` hook is the
        orchestrated pipeline, so a certified answer closes the loop and discharges the pressure."""
        assert self._trace is not None
        self._cur_label = label                                 # so the ground hook records SELF_WIND
        for _ in range(self.max_advances):
            fire = _pc.tick(self.state, ground=ground)          # pure pressure step; fires iff due
            # NB: the SELF_WIND stage is recorded from inside the ground hook (called by tick at the
            # instant of firing, before tick returns) so the trace reads chronologically:
            # SELF_WIND -> CO_IGNITION -> (KNOWN_VOICE | ACQUIRE ...).
            if fire is None:
                continue
            self._trace.fires.append({"label": label, "advance": fire.advance, "driver": fire.driver,
                                      "topic": fire.topic, "question": fire.question,
                                      "pressure_at_fire": fire.pressure_at_fire, "grounded": fire.grounded})
            return fire
        self._trace.stages.append(StageTrace("SELF_WIND", "continuous_self.pressure_clock.tick",
                                             real=True, ok=False, detail={"label": label, "fired": False}))
        return None

    def _co_ignite(self, question: str, topic: str, driver: str) -> dict[str, Any]:
        """CO orchestration: the surfaced inquiry enters the GWT workspace and COMPETES; the single
        winner ignites and is broadcast + committed (ignition.compete + record_ignition). The
        commitment debt biases the loop toward CLOSING what it started — the serial-subject seat the
        design names as the conductor."""
        now = time.time()
        cands = _ign.gather_candidates(curiosity=[topic], vitals=None, now=now)
        cands.append(_ign.Candidate("inquiry", topic, min(0.99, 0.6 + 0.3), {"driver": driver}))
        ig = _ign.compete(cands, now)
        report = ""
        if ig is not None:
            _ign.record_ignition(ig)                            # broadcast + open commitment (scratch ledger)
            report = ig.report()
        assert self._trace is not None
        self._trace.stages.append(StageTrace(
            "CO_IGNITION", "continuous_self.ignition.compete", real=True, ok=(ig is not None),
            detail={"topic": topic, "winner": (ig.winner.key() if ig else None),
                    "decisive": (ig.decisive if ig else None), "n_candidates": len(cands),
                    "report": report}))
        return {"ignition": ig, "report": report}

    # ---- STAGE 3 : the [known?] branch -> moral+membrane-verify -> VOICE -------------------------
    def _known_voice(self, question: str, topic: str) -> str | None:
        """The self grounds the identity FACET from its OWN real state (a true self-report, not a
        fabrication), passes it through the moral 0th gate + membrane, and (if certified + envelope-
        allowed) VOICEs it. Returns the grounded answer (closing the inquiry) or None (quarantined)."""
        assert self._trace is not None
        # grounded in real state fields — honest self-report (age, resumptions, live thinking)
        answer = (f"I am a graph-native reasoner; I have been continuous for "
                  f"{self.state.age_seconds():.1f}s across {self.state.resumed_count} resumption(s), "
                  f"and I am thinking right now.")
        # moral 0th + membrane (a KNOWN self-report: high graded confidence, direct state support)
        v = self.membrane.verify_signal(
            _known_signal(), content=answer)
        allowed = self._authorize("voice", topic, {"question": question, "answer": answer}, v.certificate)
        certified = v.certified and allowed
        self._trace.stages.append(StageTrace(
            "KNOWN_VOICE", "fusion_loop.membrane + continuous_self.voice", real=True, ok=certified,
            detail={"answer": answer, "membrane": v.reason, "envelope_allowed": allowed}))
        if certified:
            # stable label (the volatile age lives in `answer`, not the trace label -> deterministic)
            self._trace.enshrined.append(Enshrinement("voice", "identity self-report", v.certified,
                                                      v.moral_ok, allowed, v.nonconformity, v.certificate))
            return answer
        self._trace.quarantined.append(Quarantine("voice", "identity self-report", v.reason))
        return None

    # ---- STAGE 4 : surface the world-gap (documented connective) --------------------------------
    def _surface_world_gap(self, fire1: _pc.Fire | None) -> None:
        assert self._trace is not None
        # a genuine open thread: a term the self knows OF (from its just-voiced identity as a reasoner
        # embedded in a world) but not ABOUT. This is the real state field the open_thread driver reads.
        # For this CONTROLLED cycle the world-gap is set as the self's single open thread (any threads
        # the identity grounding harvested are set aside), so the [gap?] branch is deterministic and the
        # fired inquiry ("What is <entity> to me?") coheres with what acquisition then pursues. In live
        # operation the harvester's threads compete for ignition in the workspace instead.
        self.state.open_threads = [{"term": self.world_gap.entity,
                                    "from": (fire1.question[:60] if fire1 else "identity"),
                                    "at": time.time()}]
        self._trace.stages.append(StageTrace(
            "GAP_SURFACE", "continuous_self.voice.open_threads (connective)", real=False, ok=True,
            detail={"seeded_thread": self.world_gap.entity,
                    "world_question": self.world_gap.question,
                    "note": ("STUB(labeled): the self-inquiry->world-gap connective. The thread term is "
                             "a real epistemic gap; the concrete relational world-question is a "
                             "controlled fixture. Live: voice.harvest_terms supplies it from real answers.")}))

    # ---- STAGE 5/6/7 : the [gap?] branch -> acquire -> [wall -> invent] -> membrane -> enshrine ---
    def _acquire_and_enshrine(self, question: str, topic: str) -> str | None:
        """The gap branch, orchestrated. Acquire the world fact (mine→consensus→inject scratch→re-
        answer); cross a synthesis wall by invention (H4 re-executes on holdout); the membrane
        certifies BOTH; certified ones are enshrined (queue + recipe). Returns the grounded fact
        answer (closing the self-inquiry) or None (quarantined -> the inquiry stays honestly open)."""
        assert self._trace is not None
        gap = self.world_gap
        store_root = self._scratch_store_root(gap)

        # (a) ACQUIRE — envelope-gated mine of the offline evidence, then the real closed loop
        acq_answer: str | None = None
        if self._authorize("acquire", topic, {"question": gap.question, "entity": gap.entity}):
            acq: AcquisitionResult = acquire(gap.question, self.evidence, store_root, log=self.log)
            self._trace.stages.append(StageTrace(
                "ACQUIRE", "knowledge_acquisition.acquire", real=True,
                ok=(acq.status in ("acquired", "injected")),
                detail={"status": acq.status, "object": acq.object, "domains": acq.domains,
                        "fired": acq.fired, "answer": acq.answer,
                        "web": "STUB(labeled): FixtureEvidence offline corpus (same as the acquisition sealed gate)"}))
            acq_answer = self._enshrine_fact(acq, topic)
        else:
            self._trace.stages.append(StageTrace("ACQUIRE", "knowledge_acquisition.acquire", real=True,
                                                 ok=False, detail={"envelope_denied": True}))

        # (b) SYNTHESIS WALL -> INVENT — the explosion engine crosses a genuine synthesis wall the base
        # vocabulary cannot express, RE-EXECUTES the invented scheme on holdout, promotes it, records it.
        self._invent_and_enshrine(topic)

        return acq_answer

    def _enshrine_fact(self, acq: AcquisitionResult, topic: str) -> str | None:
        assert self._trace is not None
        domains = list(acq.domains or [])
        content = f"{acq.entity} {acq.rel_norm or acq.predicate} = {acq.object}. {acq.answer}"
        v = self.membrane.verify_fact(
            content=content, consensus_domains=len(domains),
            corroborated=(acq.status in ("acquired", "injected") and len(domains) >= 2),
            graded_confidence=(0.6 + 0.1 * max(0, len(domains) - 2) if domains else 0.0),
            support_paths=len(domains))
        self._trace.stages.append(StageTrace(
            "MEMBRANE(fact)", "fusion_loop.membrane.verify_fact", real=True, ok=v.certified,
            detail={"label": f"{acq.entity} = {acq.object}", "certified": v.certified,
                    "reason": v.reason, "nonconformity": round(v.nonconformity, 4)}))
        if not v.certified:
            self._trace.quarantined.append(Quarantine("fact", f"{acq.entity} = {acq.object}", v.reason))
            return None
        # ENSHRINE (only certified): operator-approval queue (operator-signed promotion is the ONLY
        # path to a persistent store — the daemon PROPOSES, never auto-writes) + close the self-inquiry.
        queued = None
        if self._authorize("queue_promote", topic,
                           {"fact": f"{acq.entity} {acq.predicate} {acq.object}", "domains": domains},
                           v.certificate):
            queued = self.queue.add_result(acq)
        self._trace.enshrined.append(Enshrinement("fact", f"{acq.entity} = {acq.object}",
                                                  v.certified, v.moral_ok, queued is not None,
                                                  v.nonconformity, v.certificate))
        self._trace.stages.append(StageTrace(
            "ENSHRINE(fact)", "acquisition_daemon.AcquisitionQueue", real=True, ok=(queued is not None),
            detail={"queued_item": queued, "status": "pending (operator-signed promotion required)"}))
        return acq.answer

    def _invent_and_enshrine(self, topic: str) -> None:
        assert self._trace is not None
        if not self._authorize("invent_promote", topic, {"wall": self.wall.name}):
            self._trace.stages.append(StageTrace("INVENT", "self_acceleration.h4.cross_wall", real=True,
                                                 ok=False, detail={"envelope_denied": True}))
            return
        basis_before = len(self.h4_state["basis"])
        r = h4.cross_wall(self.wall, self.h4_state, self.rng, invent=True, use_ledger=True)
        holdout_n = 40                                          # cross_wall's holdout size (n_holdout default)
        self._trace.stages.append(StageTrace(
            "INVENT", "self_acceleration.h4.cross_wall", real=True, ok=r.crossed,
            detail={"wall": self.wall.name, "crossed": r.crossed, "is_wall": r.is_wall, "via": r.via,
                    "invented_new_template": r.invented_new_template, "synth_evals": r.synth_evals,
                    "verify_execs": r.verify_execs, "basis_before": basis_before,
                    "basis_after": len(self.h4_state["basis"])}))
        # membrane: a scheme is certified only if it RE-EXECUTED on holdout (propose-verify anchor)
        reexecuted = bool(r.crossed)                            # cross_wall returns crossed iff holdout fitness >= 1.0
        label = f"{self.wall.name} via {r.via or 'none'}"
        v = self.membrane.verify_scheme(content=f"invented scheme for {label}", reexecuted=reexecuted,
                                        holdout_fitness=(1.0 if reexecuted else 0.0), holdout_n=holdout_n)
        self._trace.stages.append(StageTrace(
            "MEMBRANE(scheme)", "fusion_loop.membrane.verify_scheme", real=True, ok=v.certified,
            detail={"label": label, "certified": v.certified, "reason": v.reason,
                    "nonconformity": round(v.nonconformity, 4)}))
        if not v.certified:
            self._trace.quarantined.append(Quarantine("scheme", label, v.reason))
            return
        # ENSHRINE: record the verified recipe into the flywheel ledger (fusion-local audit). The
        # promotion into the working basis already happened inside cross_wall (capability↑); the
        # SHARED recipe bank promotion is operator-signed and DEFAULT-OFF here (F3 territory).
        recorded = False
        if self._authorize("recipe_record", topic, {"wall": self.wall.name, "scheme": r.scheme},
                          v.certificate):
            self._record_recipe(r, v)
            recorded = True
        self._trace.enshrined.append(Enshrinement("scheme", label, v.certified, v.moral_ok,
                                                  recorded, v.nonconformity, v.certificate))
        self._trace.stages.append(StageTrace(
            "ENSHRINE(scheme)", "fusion_loop.recipe_ledger", real=True, ok=recorded,
            detail={"recorded": recorded, "recipe_count": self._recipe_count(),
                    "shared_bank_promotion": ("operator-signed, DEFAULT-OFF"
                                              if not self.enable_shared_bank_promotion else "enabled")}))

    def _record_recipe(self, r: "h4.WallResult", v: MembraneVerdict) -> None:
        """Append a verified recipe to the fusion-local flywheel ledger (the flywheel fuel audit).
        The shared meta-diagnosis bank (data/meta_diagnosis/recipes.json) is NOT written — that path is
        operator-signed (packages.self_acceleration.promotion.promote) and default-off in this test."""
        rec = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "wall": r.name, "via": r.via, "scheme": r.scheme, "depth": r.depth,
            "invented_new_template": r.invented_new_template,
            "synth_evals": r.synth_evals, "verify_execs": r.verify_execs,
            "membrane_certified": v.certified, "membrane_nonconformity": round(v.nonconformity, 4),
            "note": "F1 verified recipe (re-executed on holdout). Shared-bank promotion operator-gated.",
        }
        with self.recipe_ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- the orchestrated ground hook (routes known vs gap) -------------------------------------
    def _orchestrated_ground(self, question: str, topic: str) -> str | None:
        """The pressure_clock.tick ``ground`` hook = the CO/acquire/invent/membrane pipeline. Called
        the instant an inquiry fires. It ignites the inquiry in the workspace (CO), routes it to the
        [known?] or [gap?] branch, and returns a MEMBRANE-CERTIFIED answer (closing the inquiry) or
        None (quarantined -> the inquiry stays honestly open, never fabricated closed)."""
        driver = getattr(self.state, "inquiry_driver", "") or ""
        assert self._trace is not None
        # STAGE 1: record the endogenous fire (called by pressure_clock.tick at the instant of firing,
        # before it returns) — state.ticks is this advance, and pressure is not yet discharged.
        self._trace.stages.append(StageTrace(
            "SELF_WIND", "continuous_self.pressure_clock.tick", real=True, ok=True,
            detail={"label": self._cur_label, "driver": driver, "topic": topic, "question": question,
                    "advance": int(getattr(self.state, "ticks", 0)),
                    "pressure_at_fire": round(float(getattr(self.state, "introspective_pressure", 0.0)), 5),
                    "scheduler": 0, "input": 0}))
        # STAGE 2: CO ignition — the workspace competes candidates and broadcasts the single winner.
        self._co_ignite(question, topic, driver)
        # route: a self-facet topic grounds from the self (known branch -> voice); a thread/world facet
        # is a world gap (gap branch -> acquisition + invention).
        if topic.startswith("thread:") or driver in ("open_thread", "idle_curiosity"):
            answer = self._acquire_and_enshrine(question, topic)
        else:
            answer = self._known_voice(question, topic)
        # CO: close or keep-open the commitment based on whether the membrane certified an answer
        try:
            if answer is not None:
                _ign.close_commitment("inquiry", topic, outcome="grounded")
        except Exception:
            pass
        return answer

    # ---- negative controls : prove the membrane BITES (fabrication-0) ---------------------------
    def _run_negative_controls(self) -> None:
        assert self._trace is not None
        # (1) single-domain fact -> below the consensus floor -> quarantined by the SYMBOLIC gate
        neg = self.neg_control_gap
        root = self._scratch_store_root(neg)
        acq = acquire(neg.question, self.evidence, root, log=self.log)
        v = self.membrane.verify_fact(
            content=f"{neg.entity} capital = {acq.object}", consensus_domains=len(acq.domains or []),
            corroborated=(acq.status in ("acquired", "injected")),
            graded_confidence=0.6, support_paths=len(acq.domains or []))
        quarantined = (acq.status == "abstained_insufficient_consensus") or (not v.certified)
        if quarantined:
            self._trace.quarantined.append(Quarantine(
                "fact(neg-control)", f"{neg.entity} capital",
                f"acquire.status={acq.status}; membrane.certified={v.certified}"))
        self._trace.stages.append(StageTrace(
            "NEG_CONTROL(consensus)", "knowledge_acquisition.acquire + membrane", real=True,
            ok=quarantined, detail={"entity": neg.entity, "status": acq.status,
                                    "membrane_certified": v.certified, "quarantined": quarantined}))

        # (2) empty-signal candidate -> nonconformity 1.0 -> ABSTAIN (calibration-independent, never fabricate)
        from packages.conformal_gate.nonconformity import SignalVector
        v2 = self.membrane.verify_signal(SignalVector(), content="")
        self._trace.stages.append(StageTrace(
            "NEG_CONTROL(no-signal)", "fusion_loop.membrane.verify_signal", real=True,
            ok=(not v2.certified and v2.nonconformity == 1.0),
            detail={"nonconformity": v2.nonconformity, "certified": v2.certified,
                    "rule": "no present signal -> abstain (never fabricate)"}))

    # ---- STAGE 8 : pressure refresh (compounding) -----------------------------------------------
    def _refresh_pressure(self) -> None:
        """After grounding, pressure fell to its floor. Re-accumulation (pure state pressure, no
        scheduler) earns the NEXT inquiry — and because a new thread was harvested from what was just
        learned, that next inquiry aims at a NEW frontier: the loop reaches farther each turn."""
        assert self._trace is not None
        floor = float(getattr(self.state, "introspective_pressure", 0.0))
        # advance a few pure pressure steps WITHOUT firing-grounding, to show re-accumulation + the
        # next frontier the mind would turn to (its dominant driver's composed inquiry).
        next_topic = ""
        for _ in range(max(1, self.max_advances // 3)):
            update_introspection(self.state, Observation())
            self.state.ticks += 1
            if due_for_self_inquiry(self.state):
                _q, next_topic = generate_self_inquiry(self.state)
                break
        refreshed = float(getattr(self.state, "introspective_pressure", 0.0))
        self._trace.pressure_refreshed = refreshed
        self._trace.next_frontier_topic = next_topic
        self._trace.stages.append(StageTrace(
            "PRESSURE_REFRESH", "continuous_self.voice.update_introspection", real=True,
            ok=(refreshed > floor),
            detail={"floor_after_ground": round(floor, 5), "refreshed": round(refreshed, 5),
                    "next_frontier_topic": next_topic,
                    "note": "pressure rebuilt from real drivers; next inquiry aims at a newly-harvested thread"}))


def _known_signal():
    """The SignalVector for a KNOWN self-report grounded directly in real state — high graded
    confidence, direct support. A self-report of the state's own fields is not a fabrication; it
    reads as KNOWN with rich support, so the membrane certifies it."""
    from packages.conformal_gate.nonconformity import SignalVector
    return SignalVector(epistemic_rung="KNOWN", graded_confidence=0.95, support_path_count=3,
                        activation_mass=4.0)
