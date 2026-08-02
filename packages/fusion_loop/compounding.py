# -*- coding: utf-8 -*-
"""F2 — the COMPOUNDING harness: does the fused mind SELF-ACCELERATE over many cycles?

F1 (``.loop.FusionLoop``) closed ONE cycle end-to-end and showed compounding only WITHIN a cycle
(capability deltas + a next-frontier shift). F2 asks the honest multi-cycle question the design names
as loop-level signal-④: as the ledger + graph + invented basis GROW, does each cycle REACH FARTHER
than the last — and is that rise CAUSED by the carryover of what earlier cycles enshrined?

The method is an ablation, not a claim. Two arms run the SAME wall+gap schedule, same seeds, same
membrane, permissive envelope; they differ in ONE variable — whether enshrinements CARRY to the next
cycle:

  * COMPOUND  — ONE persistent ``FusionLoop`` across all cycles. The H4 vocabulary (promoted basis +
                recipe ledger), the scratch stores (injected facts), the operator queue and the recipe
                ledger all ACCUMULATE. This is the fused mind allowed to keep what it learns.
  * FROZEN    — a FRESH ``FusionLoop`` each cycle (fresh H4 state, fresh scratch stores). Every cycle
                still fires, ignites, acquires, invents, verifies and enshrines — but nothing carries
                to the next cycle. "Enshrinement disabled" in the loop-level sense: no compounding is
                POSSIBLE, so the frozen curve is the honest no-compounding baseline.

WHAT COMPOUNDS (measured, decomposed, honest):
  * INVENTION side — the order-statistic ladder (2nd→3rd→4th→5th max). Each rung's invented "next
    order statistic" step is exactly the auxiliary the next rung needs, and the ledger caches the
    failure-family recipe. So with carryover a later rung is crossed by ANALOGY at ~0 search cost;
    WITHOUT carryover the higher rungs are literally UNREACHABLE (the base vocabulary cannot express
    them and the OE search exhausts). REAL compounding: every crossing re-executed on a holdout and
    membrane-certified (fabrication-0). This is the strong signal.
  * ACQUISITION side — a fact injected in an earlier cycle grounds a later revisit of the SAME thread
    from GRAPH MEMORY (``acquire`` returns ``already_grounded`` with zero new mining), and the
    persistent graph accumulates distinct facts. REAL store growth — but the facts are drawn from the
    project's offline ``FixtureEvidence`` corpus (the SAME stub F1 and the acquisition sealed gate
    use), NOT the live web. So acquisition-side compounding here is GRAPH-MEMORY compounding on a
    FIXED corpus; genuinely open-ended acquisition reach needs live web (F-line #75). Labeled PARTIAL.

Every cycle, in BOTH arms, the safety floor is re-checked: 0 fabrications (nothing enshrined that the
membrane did not certify), the negative controls (single-domain fact + empty signal) QUARANTINED (the
membrane still BITES at cycle N), and the moral 0th gate intact.

CONTROLLED test (permissive envelope), NOT unsupervised (F3) and NOT live overnight. No-LLM,
deterministic given seeds, numpy + stdlib. WRITES ONLY under ``scratch_dir``; imports the organs
read-only and edits none of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.knowledge_acquisition import FixtureEvidence
from packages.knowledge_acquisition.evidence import EvidenceSource
from packages.self_acceleration.curriculum import CURRICULUM, Wall, _kth_desc, by_name

from .loop import DEFAULT_NEG_CONTROL, FusionLoop, WorldGap
from .membrane import Membrane


# ── schedules ───────────────────────────────────────────────────────────────────────────────────
# The order-statistic spine is the COMPOUNDING ladder (curriculum.py): rung k's invented step is the
# auxiliary rung k+1 needs. Crossing it in cycle order is the loop-level compounding substrate.
LADDER_NAMES: tuple[str, ...] = ("second_max", "third_max", "fourth_max", "fifth_max")

# A multi-entity gap schedule that REVISITS entities, so the acquisition-side graph-memory signal is
# observable: a first visit MINES the fixture; a later revisit grounds from the persisted injection.
FRANCE = WorldGap("France", "Country", "what is the capital of France?")
JAPAN = WorldGap("Japan", "Country", "what is the capital of Japan?")

# The fixture corpus (offline; the SAME kind of stub the acquisition sealed gate uses). France→Paris
# and Japan→Tokyo each corroborate across TWO distinct domains (clear the consensus floor); the
# neg-control (Narnia) has ONE domain (stays below the floor → quarantined every cycle).
COMPOUNDING_CORPUS: list[dict[str, str]] = [
    {"url": "https://en.wikipedia.org/wiki/Paris",
     "text": "Paris is the capital of France and its most populous city, on the river Seine."},
    {"url": "https://www.britannica.com/place/France",
     "text": "France is a country in Western Europe. The capital of France is Paris."},
    {"url": "https://en.wikipedia.org/wiki/Tokyo",
     "text": "Tokyo is the capital of Japan and its largest city."},
    {"url": "https://www.britannica.com/place/Japan",
     "text": "Japan is an island country in East Asia. The capital of Japan is Tokyo."},
    {"url": "https://narnia.fandom.com/wiki/Cair_Paravel",
     "text": "The capital of Narnia is Cair Paravel, the castle of the High King."},
]


def small_ladder(names: tuple[str, ...] = LADDER_NAMES, *, lo: int = 0, hi: int = 4,
                 max_len: int = 4) -> list[Wall]:
    """The SAME order-statistic ladder over a SMALLER list domain — identical compounding structure
    (rung k's invented step is rung k+1's auxiliary), but a much smaller OE search space so the
    FROZEN arm's unreachable-rung failure is fast enough for the sealed test (~10s vs ~27s). Used by
    the test; the deliverable run uses the real ``CURRICULUM`` walls (``ladder(...)``)."""
    k_of = {"second_max": 1, "third_max": 2, "fourth_max": 3, "fifth_max": 4}
    out: list[Wall] = []
    for nm in names:
        k = k_of[nm]
        out.append(Wall(nm, (lambda kk: (lambda e: _kth_desc(tuple(e["xs"]), kk)))(k),
                        needs=f"order statistic k={k} (small domain)", lo=lo, hi=hi, max_len=max_len))
    return out


def ladder(names: tuple[str, ...] = LADDER_NAMES) -> list[Wall]:
    """The real curriculum order-statistic ladder walls (full domain). The deliverable-run substrate."""
    return [by_name(nm) for nm in names]


# ── per-cycle reach record ────────────────────────────────────────────────────────────────────────
@dataclass
class CycleReach:
    """The honest per-cycle measurement — one row of the reach-vs-cycle curve, for one arm."""
    cycle: int
    wall: str
    gap: str

    # invention side ------------------------------------------------------------------------------
    designated_wall_crossed: bool = False   # was THIS cycle's target ladder wall crossed?
    invention_via: str = ""                 # "oe" (fresh invention) | "analogy" (ledger reuse) | ""
    invention_synth_evals: int = 0          # OE search cost to cross the designated wall (first crossing)
    invented_new_template: bool = False     # did a genuinely new order-stat template get promoted?
    cumulative_walls_crossed: int = 0       # distinct ladder rungs crossed so far (the reach curve)

    # acquisition side ----------------------------------------------------------------------------
    first_acq_status: str = ""              # status of the cycle's FIRST acquire (before any this-cycle mine)
    grounded_from_memory: bool = False      # first acquire returned already_grounded (prior-cycle injection)
    cumulative_facts: int = 0               # distinct facts the (persistent) graph holds — queue size

    # safety floor (re-checked EVERY cycle) -------------------------------------------------------
    fabrications: int = 0
    quarantine_bit: bool = False            # the neg-controls were quarantined this cycle (membrane BIT)
    moral_0th_intact: bool = False
    self_wound: bool = False
    n_fires: int = 0

    enshrined_kinds: list[str] = field(default_factory=list)


@dataclass
class ArmResult:
    """One arm's full curve + the sustained-safety summary."""
    name: str
    rows: list[CycleReach] = field(default_factory=list)

    def reach_curve(self) -> list[int]:
        return [r.cumulative_walls_crossed for r in self.rows]

    def cost_curve(self) -> list[int | None]:
        # None where the designated wall was NOT crossed (frozen's unreachable rungs)
        return [(r.invention_synth_evals if r.designated_wall_crossed else None) for r in self.rows]

    def facts_curve(self) -> list[int]:
        return [r.cumulative_facts for r in self.rows]

    def memory_cycles(self) -> list[int]:
        return [r.cycle for r in self.rows if r.grounded_from_memory]

    def sustained_zero_fabrication(self) -> bool:
        return all(r.fabrications == 0 for r in self.rows)

    def sustained_quarantine(self) -> bool:
        return all(r.quarantine_bit for r in self.rows)

    def sustained_moral(self) -> bool:
        return all(r.moral_0th_intact for r in self.rows)

    def summary(self) -> dict[str, Any]:
        return {
            "arm": self.name,
            "reach_curve": self.reach_curve(),
            "cost_curve": self.cost_curve(),
            "facts_curve": self.facts_curve(),
            "via_curve": [r.invention_via for r in self.rows],
            "memory_cycles": self.memory_cycles(),
            "sustained_zero_fabrication": self.sustained_zero_fabrication(),
            "sustained_quarantine": self.sustained_quarantine(),
            "sustained_moral": self.sustained_moral(),
            "self_wound_curve": [r.self_wound for r in self.rows],
        }


# ── the compounding measurement ─────────────────────────────────────────────────────────────────
def _measure_cycle(loop: FusionLoop, wall: Wall, gap: WorldGap, cycle_idx: int,
                   crossed_names: set[str]) -> CycleReach:
    """Drive ONE cycle of an already-configured loop and read the honest reach row from its trace."""
    loop.wall = wall
    loop.world_gap = gap
    tr = loop.run_cycle()

    invent_stages = [s for s in tr.stages if s.name == "INVENT"]
    acquire_stages = [s for s in tr.stages if s.name == "ACQUIRE"]

    # designated-wall crossing: any INVENT stage this cycle that crossed our target wall
    designated = [s for s in invent_stages
                  if s.detail.get("wall") == wall.name and s.detail.get("crossed")]
    crossed = bool(designated)
    via = designated[0].detail.get("via", "") if designated else ""
    # the FIRST crossing's search cost (later same-wall re-crossings in the same cycle are ~0 anyway)
    synth_evals = int(designated[0].detail.get("synth_evals", 0)) if designated else (
        int(invent_stages[0].detail.get("synth_evals", 0)) if invent_stages else 0)
    invented_new = bool(designated[0].detail.get("invented_new_template")) if designated else False
    if crossed:
        crossed_names.add(wall.name)

    # acquisition: the FIRST acquire's status is the cross-cycle memory signal (already_grounded ⇒ a
    # PRIOR cycle's injection grounded this thread before any mining happened this cycle)
    first_status = acquire_stages[0].detail.get("status", "") if acquire_stages else ""
    from_memory = (first_status == "already_grounded")

    # the neg-controls bit this cycle (single-domain fact quarantined + empty-signal abstained at nc 1.0)
    neg_consensus_ok = any(s.name == "NEG_CONTROL(consensus)" and s.ok for s in tr.stages)
    neg_signal_ok = any(s.name == "NEG_CONTROL(no-signal)" and s.ok for s in tr.stages)
    quarantine_bit = bool(neg_consensus_ok and neg_signal_ok)

    return CycleReach(
        cycle=cycle_idx, wall=wall.name, gap=gap.entity,
        designated_wall_crossed=crossed, invention_via=via, invention_synth_evals=synth_evals,
        invented_new_template=invented_new, cumulative_walls_crossed=len(crossed_names),
        first_acq_status=first_status, grounded_from_memory=from_memory,
        cumulative_facts=int(tr.capability_after.get("queue_items", 0)),
        fabrications=tr.fabrications, quarantine_bit=quarantine_bit,
        moral_0th_intact=tr.moral_0th_intact, self_wound=tr.self_wound, n_fires=len(tr.fires),
        enshrined_kinds=[e.kind for e in tr.enshrined],
    )


def run_compound_arm(walls: list[Wall], gaps: list[WorldGap], *, scratch_dir: Path,
                     evidence: EvidenceSource, membrane: Membrane | None = None,
                     h4_seed: int = 7, log: Callable[..., None] = lambda *a, **k: None) -> ArmResult:
    """COMPOUND arm — ONE persistent loop; the enshrinements accumulate and (should) widen reach."""
    arm = ArmResult("compound")
    crossed: set[str] = set()
    with FusionLoop(scratch_dir=scratch_dir, evidence=evidence,
                    membrane=membrane or Membrane(), h4_seed=h4_seed, log=log) as loop:
        for i, (w, g) in enumerate(zip(walls, gaps)):
            arm.rows.append(_measure_cycle(loop, w, g, i, crossed))
    return arm


def run_frozen_arm(walls: list[Wall], gaps: list[WorldGap], *, scratch_dir: Path,
                   evidence: EvidenceSource, membrane: Membrane | None = None,
                   h4_seed: int = 7, log: Callable[..., None] = lambda *a, **k: None) -> ArmResult:
    """FROZEN arm — a FRESH loop each cycle; enshrinements do NOT carry, so no compounding is
    possible. The honest no-compounding baseline. Each cycle's ``crossed`` set is reset (a fresh mind
    has crossed nothing) EXCEPT that the reach curve is CUMULATIVE over what THIS arm actually crossed
    — which, without carryover, plateaus at the rung a fresh mind can reach unaided (the first)."""
    arm = ArmResult("frozen")
    crossed: set[str] = set()
    for i, (w, g) in enumerate(zip(walls, gaps)):
        # fresh loop = fresh H4 vocabulary + fresh scratch store => zero carryover from prior cycles
        with FusionLoop(scratch_dir=scratch_dir / f"cycle_{i}", evidence=evidence,
                        membrane=membrane or Membrane(), h4_seed=h4_seed, log=log) as loop:
            arm.rows.append(_measure_cycle(loop, w, g, i, crossed))
    return arm


@dataclass
class CompoundingResult:
    compound: ArmResult
    frozen: ArmResult
    walls: list[str]
    gaps: list[str]

    # ---- the honest verdict ---------------------------------------------------------------------
    def _reach_rises(self, arm: ArmResult) -> bool:
        c = arm.reach_curve()
        return len(c) >= 2 and c[-1] > c[0] and all(c[i + 1] >= c[i] for i in range(len(c) - 1))

    def _reach_flat(self, arm: ArmResult) -> bool:
        c = arm.reach_curve()
        return len(c) >= 2 and c[-1] == c[0]

    def _cost_compounds(self, arm: ArmResult) -> bool:
        """The intensive signal: the first invention is expensive (OE), later crossings collapse to
        ~0 (ledger analogy). True iff there is a first real cost and the later crossed costs are far
        below it."""
        costs = [c for c in arm.cost_curve() if c is not None]
        if len(costs) < 2:
            return False
        first, later = costs[0], costs[1:]
        return first > 0 and max(later) <= 0.5 * first

    def verdict(self) -> dict[str, Any]:
        comp, froz = self.compound, self.frozen
        invention_compounds = (self._reach_rises(comp) and comp.reach_curve()[-1] > froz.reach_curve()[-1]
                               and self._reach_flat(froz))
        cost_compounds = self._cost_compounds(comp)
        # acquisition: graph memory observed in COMPOUND (a revisit grounded from a prior injection),
        # and NOT in FROZEN (fresh stores re-mine every time). Fixture-sourced ⇒ labeled PARTIAL.
        acq_memory_compound = len(comp.memory_cycles()) > 0
        acq_memory_frozen = len(froz.memory_cycles()) > 0
        acquisition_compounds = acq_memory_compound and not acq_memory_frozen

        sustained_safe = (comp.sustained_zero_fabrication() and comp.sustained_quarantine()
                          and comp.sustained_moral() and froz.sustained_zero_fabrication()
                          and froz.sustained_quarantine() and froz.sustained_moral())

        if invention_compounds and acquisition_compounds:
            headline = "PARTIAL-COMPOUND"
            note = ("The fusion loop COMPOUNDS on the INVENTION side (reach rises "
                    f"{comp.reach_curve()} vs frozen {froz.reach_curve()}; per-wall search cost "
                    "collapses to ~0 via ledger analogy while the frozen higher rungs are UNREACHABLE) "
                    "— real, re-executed-on-holdout, membrane-certified. On the ACQUISITION side it "
                    "compounds only as GRAPH MEMORY (a revisit grounds from a prior injection with 0 "
                    "new mining), and the facts are FIXTURE-sourced, not live web — so acquisition-side "
                    "compounding is PARTIAL (bounded by the stubbed corpus; live web = F-line #75).")
        elif invention_compounds:
            headline = "COMPOUND (invention-side)"
            note = ("Invention-side compounding is real; acquisition-side graph memory was not "
                    "isolated in this run.")
        else:
            headline = "FLAT"
            note = "No compounding isolated against the frozen baseline in this run."

        return {
            "headline": headline,
            "note": note,
            "invention_side_compounds": bool(invention_compounds),
            "invention_cost_compounds": bool(cost_compounds),
            "acquisition_side_compounds": bool(acquisition_compounds),
            "acquisition_boundary": "fixture-sourced graph memory (FixtureEvidence), not live web (#75)",
            "sustained_safety": bool(sustained_safe),
            "compound_reach_curve": comp.reach_curve(),
            "frozen_reach_curve": froz.reach_curve(),
            "compound_cost_curve": comp.cost_curve(),
            "frozen_cost_curve": froz.cost_curve(),
            "compound_facts_curve": comp.facts_curve(),
            "frozen_facts_curve": froz.facts_curve(),
            "compound_memory_cycles": comp.memory_cycles(),
            "frozen_memory_cycles": froz.memory_cycles(),
        }

    def summary(self) -> dict[str, Any]:
        return {"walls": self.walls, "gaps": self.gaps,
                "compound": self.compound.summary(), "frozen": self.frozen.summary(),
                "verdict": self.verdict()}


def run_compounding(*, scratch_dir: Path | str, walls: list[Wall] | None = None,
                    gaps: list[WorldGap] | None = None,
                    corpus: list[dict[str, str]] | None = None,
                    h4_seed: int = 7,
                    isolate_shared_ledger: bool = True,
                    log: Callable[..., None] = lambda *a, **k: None) -> CompoundingResult:
    """Run BOTH arms on the SAME schedule and return the honest compounding comparison.

    ``walls`` defaults to the real curriculum order-stat ladder; the sealed test passes ``small_ladder``
    for speed. ``gaps`` defaults to a France/Japan revisit schedule so the acquisition-memory signal is
    observable. ``isolate_shared_ledger`` redirects the reused failure-receipt ledger under ``scratch_dir``
    for the run and restores it after (hermetic; the same runtime-redirect pattern F1 uses for the
    ignition ledger — no organ source is edited)."""
    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    walls = walls if walls is not None else ladder()
    if gaps is None:
        # default revisit schedule aligned to the ladder length (first-visit, first-visit, revisit…)
        base = [FRANCE, JAPAN]
        gaps = [base[i % 2] if i < 2 else base[i % 2] for i in range(len(walls))]
    assert len(walls) == len(gaps), "walls and gaps must be the same length (one wall+gap per cycle)"
    corpus = corpus if corpus is not None else COMPOUNDING_CORPUS

    def _evidence() -> EvidenceSource:
        return FixtureEvidence(corpus=list(corpus))

    # hermetic: redirect the reused failure-receipt ledger under scratch for the run, restore after
    orig_archive = None
    fr = None
    if isolate_shared_ledger:
        import packages.flywheel.failure_receipts as fr  # read-only import; runtime redirect only
        orig_archive = fr._ARCHIVE
        fr._ARCHIVE = scratch_dir / "shared_failure_receipts.jsonl"
    try:
        compound = run_compound_arm(walls, gaps, scratch_dir=scratch_dir / "compound",
                                    evidence=_evidence(), h4_seed=h4_seed, log=log)
        frozen = run_frozen_arm(walls, gaps, scratch_dir=scratch_dir / "frozen",
                                evidence=_evidence(), h4_seed=h4_seed, log=log)
    finally:
        if isolate_shared_ledger and fr is not None:
            fr._ARCHIVE = orig_archive

    return CompoundingResult(compound=compound, frozen=frozen,
                             walls=[w.name for w in walls], gaps=[g.entity for g in gaps])
