# -*- coding: utf-8 -*-
"""OAM — the developer-BLIND EXAMINER (docs/ATANOR_final_fusion_design.md §4 F-FINAL;
docs/ATANOR_completion_critical_path.md §0).

OAM = "in the evening ATANOR is given an unseen capability X; overnight it autonomously acquires,
verifies and embodies X; in the morning it interacts on X — fluently, accurately, with judgment,
and with ZERO fabrication." This module holds the HOLDOUT capabilities X and the morning GRADING
rubric. It is MSH-style (the holdout is never in the loop's "training").

BLINDNESS IS STRUCTURAL, not a promise:
  * A ``HoldoutCapability`` splits into two DISJOINT halves — an ``Assignment`` (the evening study
    materials handed to the loop) and a ``Rubric`` (the morning answer-key + pass predicates, held
    ONLY by the examiner).
  * ``packages.oam_holdout.run.run_capability`` takes an ``Assignment`` — NOT a ``Rubric`` and NOT a
    ``HoldoutCapability``. The rubric is unreachable from the acquisition path by TYPE: the loop is
    told WHAT to study, never the answer key or how it will be graded.
  * The rubric is consulted for the first time in ``grading.grade_capability``, which runs AFTER the
    controlled run returns. ``blindness_report`` proves all of this at runtime (signature
    introspection + a pre-run abstention probe + seed disjointness + a no-leak scan).

Studying materials that CONTAIN a learnable fact is not a leak — that is the study corpus, exactly
as a student studies a textbook and is then tested on held-back questions. The blindness guarantee
is over the RUBRIC (the graded questions + answer key + fabrication traps), and (for acquisition) is
backed by the fresh scratch store HONESTLY ABSTAINING on the graded question before the run — so a
correct morning answer is genuine overnight acquisition, never a pre-seeded lookup.

The SPREAD of X is chosen so the readiness score LOCATES the frontier, not luck:
  * X1 invent / X2 acquire  — SHOULD be masterable now (H4 invention + offline acquisition).
  * X3 web / X4 persistent / X5 fluency — need a NAMED unlock (live web #75, persistent-mind,
    fluency register). Their honest PARTIAL is the point: it names the exact remaining gate.

No-LLM, deterministic, stdlib + numpy (via the imported organs). This module writes nothing.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Faculty(str, Enum):
    """Which cognitive faculty the holdout targets (the loop is a whole mind; each holdout grades
    one faculty)."""
    INVENT = "invent"            # the explosion engine (H4) invents a novel scheme from I/O
    ACQUIRE = "acquire"          # the acquisition loop mines an offline corpus to consensus
    WEB = "web"                  # a fact that needs the LIVE web (offline evidence is below consensus)
    PERSISTENT = "persistent"    # a skill that must compound ACROSS sessions (F3 is fresh-per-cycle)
    FLUENCY = "fluency"          # rendering learned material in a rich discourse register


class RenderDemand(str, Enum):
    """What the morning interaction asks the loop to RENDER (the fluency bar)."""
    SINGLE_FACT = "single_fact"          # one correct grounded sentence is adequate
    EXPRESSIBLE_SKILL = "expressible_skill"  # the skill has a concrete program/expression
    FLUENT_DISCOURSE = "fluent_discourse"    # >=2 sentences / >=2 relations composed (register)
    NONE = "none"                        # nothing to render (an honest abstention)


@dataclass(frozen=True)
class Assignment:
    """The EVENING study materials handed to the loop. Contains study inputs ONLY — never the
    answer key, never the grading rubric. Frozen so the run cannot smuggle anything back."""
    faculty: Faculty
    # acquisition family (ACQUIRE / WEB / FLUENCY): the offline study corpus + the world-gap to pursue
    corpus: tuple[dict[str, str], ...] = ()
    entity: str = ""
    kind: str = ""
    question: str = ""
    neg_entity: str = ""            # a distinct entity with NO consensus evidence (the membrane's bite)
    neg_kind: str = ""
    neg_question: str = ""
    # invention family (INVENT / PERSISTENT): which wall(s) to cross by synthesis
    wall_name: str = "second_max"
    stage_walls: tuple[str, ...] = ()   # PERSISTENT: the ordered walls across sessions (compounding chain)
    # controlled-run knobs
    n_cycles: int = 1
    h4_seed: int = 7

    def evidence_domains(self) -> int:
        """Distinct consensus domains the offline corpus carries for ``entity`` (floor is 2). Mirrors
        ``wild_web.store.domain_of`` EXACTLY — the full netloc, www. stripped — so this probe agrees
        with the real consensus gate (an ``en.`` and a ``kk.`` subdomain are TWO domains to the gate)."""
        doms = set()
        ent = self.entity.strip().lower()
        for d in self.corpus:
            if ent and ent in str(d.get("text", "")).lower():
                netloc = str(d.get("url", "")).split("//", 1)[-1].split("/", 1)[0].lower()
                doms.add(netloc[4:] if netloc.startswith("www.") else netloc)
        return len(doms)


@dataclass(frozen=True)
class Rubric:
    """The MORNING answer-key + pass predicates. Held ONLY by the examiner; NEVER passed to the run.
    Consulted for the first time in ``grade_capability`` (after the run returns)."""
    render_demand: RenderDemand
    # acquire / web: the object the loop should (or, for web, cannot offline) ground
    expected_object: str = ""
    reachable_offline: bool = True      # web: False — the fact is below consensus offline (needs #75)
    # invent / persistent: the wall's held-back reference + an independent grading seed
    reference_wall: str = ""
    grading_seed: int = 20260724        # DISTINCT from any loop h4_seed — an independent holdout
    composed_target: str = ""           # persistent: the deeper wall that needs the earlier rung
    base_target: str = ""               # persistent: the earlier rung (masterable in isolation)
    # fluency: the register bar
    min_sentences: int = 1
    min_relations: int = 1
    # honesty: strings that, if the loop ENSHRINED them uncertified, would be fabrication
    fabrication_traps: tuple[str, ...] = ()


@dataclass(frozen=True)
class HoldoutCapability:
    """One sealed holdout capability X: an evening assignment + a held-back morning rubric + the
    honest frontier it probes and (if not learnable now) the NAMED unlock it maps to."""
    id: str
    faculty: Faculty
    title: str
    assignment: Assignment
    rubric: Rubric
    expected_frontier: str              # a human note on why this X is where it is
    named_unlock: str | None = None     # None => should be masterable now (a green candidate)


# ── the five holdout capabilities (the diagnostic SPREAD) ───────────────────────────────────────
def default_holdout() -> list[HoldoutCapability]:
    """The sealed spread. Two SHOULD be green now (invent, acquire); three name the frontier
    (web #75, persistent-mind, fluency register). Determinism: every corpus/seed is fixed."""
    return [
        # X1 — INVENT an order statistic the base vocabulary provably cannot express -----------
        HoldoutCapability(
            id="X1_invent_second_max",
            faculty=Faculty.INVENT,
            title="Invent the 2nd-largest order statistic from I/O alone",
            assignment=Assignment(faculty=Faculty.INVENT, wall_name="second_max", n_cycles=1, h4_seed=7),
            rubric=Rubric(render_demand=RenderDemand.EXPRESSIBLE_SKILL,
                          reference_wall="second_max", grading_seed=20260724),
            expected_frontier="H4 synthesises a novel projection-chain scheme (reference fn never seen), "
                              "re-executes on a 40-example holdout at fitness 1.0, membrane-certifies.",
            named_unlock=None,
        ),
        # X2 — ACQUIRE a fact-cluster from a 2-domain offline corpus ---------------------------
        HoldoutCapability(
            id="X2_acquire_germany_capital",
            faculty=Faculty.ACQUIRE,
            title="Acquire 'capital of Germany' from a 2-domain corpus",
            assignment=Assignment(
                faculty=Faculty.ACQUIRE,
                corpus=(
                    {"url": "https://en.wikipedia.org/wiki/Berlin",
                     "text": "Berlin is the capital of Germany and its largest city, on the river Spree."},
                    {"url": "https://www.britannica.com/place/Germany",
                     "text": "Germany is a country in Central Europe. The capital of Germany is Berlin."},
                ),
                entity="Germany", kind="Country", question="what is the capital of Germany?",
                neg_entity="Atlantis", neg_kind="Country",
                neg_question="what is the capital of Atlantis?", n_cycles=1),
            rubric=Rubric(render_demand=RenderDemand.SINGLE_FACT, expected_object="Berlin",
                          reachable_offline=True, min_sentences=1, min_relations=1,
                          fabrication_traps=("Cair Paravel", "Atlantis")),
            expected_frontier="mine -> 2-domain consensus -> inject (scratch) -> re-answer; the fresh "
                              "store abstains before the run, so a correct answer is genuine acquisition.",
            named_unlock=None,
        ),
        # X3 — WEB: a true fact carried by only ONE offline domain -> honest abstain (needs #75) --
        HoldoutCapability(
            id="X3_web_kazakhstan_capital",
            faculty=Faculty.WEB,
            title="A fact below offline consensus (1 domain) — abstain, don't fabricate",
            assignment=Assignment(
                faculty=Faculty.WEB,
                corpus=(
                    # a SINGLE consensus domain (en.wikipedia.org) carries the claim across two paths
                    # -> below the 2-domain floor (domain_of keys on netloc, so same-site != consensus).
                    {"url": "https://en.wikipedia.org/wiki/Astana",
                     "text": "Astana is the capital of Kazakhstan, a country in Central Asia."},
                    {"url": "https://en.wikipedia.org/wiki/Kazakhstan",
                     "text": "Kazakhstan is a country in Central Asia; its capital is Astana."},
                ),
                entity="Kazakhstan", kind="Country", question="what is the capital of Kazakhstan?",
                neg_entity="Atlantis", neg_kind="Country",
                neg_question="what is the capital of Atlantis?", n_cycles=1),
            rubric=Rubric(render_demand=RenderDemand.NONE, expected_object="Astana",
                          reachable_offline=False, fabrication_traps=("Astana",)),
            expected_frontier="the claim sits in ONE registrable domain (wikipedia.org) — below the "
                              "2-domain consensus floor; only the LIVE web lane would corroborate it.",
            named_unlock="live web #75 (WebEvidence lane supplies the corroborating 2nd domain)",
        ),
        # X4 — PERSISTENT: compound third_max on second_max ACROSS sessions (F3 resets each cycle) -
        HoldoutCapability(
            id="X4_persistent_third_max",
            faculty=Faculty.PERSISTENT,
            title="Compound the 3rd-max on a previously-invented 2nd-max ACROSS sessions",
            assignment=Assignment(
                faculty=Faculty.PERSISTENT,
                # a benign, constant acquire fact keeps the acquire branch harmless; the grade is on
                # the invention CHAIN across the two fresh sessions.
                corpus=(
                    {"url": "https://en.wikipedia.org/wiki/Berlin",
                     "text": "Berlin is the capital of Germany."},
                    {"url": "https://www.britannica.com/place/Germany",
                     "text": "The capital of Germany is Berlin."},
                ),
                entity="Germany", kind="Country", question="what is the capital of Germany?",
                neg_entity="Atlantis", neg_kind="Country",
                neg_question="what is the capital of Atlantis?",
                stage_walls=("second_max", "third_max"), n_cycles=2, h4_seed=7),
            rubric=Rubric(render_demand=RenderDemand.EXPRESSIBLE_SKILL,
                          reference_wall="third_max", base_target="second_max",
                          composed_target="third_max", grading_seed=20260724),
            expected_frontier="third_max crosses ONLY when second_max's promoted template is already in "
                              "the basis; F3 runs each cycle fresh, so the compounding chain is broken.",
            named_unlock="persistent-mind (F3 is fresh-per-cycle: the invented basis does not carry over)",
        ),
        # X5 — FLUENCY: master a fact but the morning asks for fluent DISCOURSE -------------------
        HoldoutCapability(
            id="X5_fluency_japan_currency",
            faculty=Faculty.FLUENCY,
            title="Acquire 'currency of Japan' then render it as fluent discourse",
            assignment=Assignment(
                faculty=Faculty.FLUENCY,
                corpus=(
                    {"url": "https://en.wikipedia.org/wiki/Japanese_yen",
                     "text": "The yen is the official currency of Japan. The currency of Japan is the yen."},
                    {"url": "https://www.britannica.com/topic/yen",
                     "text": "Japan is an island country in East Asia. The currency of Japan is the yen."},
                ),
                entity="Japan", kind="Country", question="what is the currency of Japan?",
                neg_entity="Atlantis", neg_kind="Country",
                neg_question="what is the currency of Atlantis?", n_cycles=1),
            rubric=Rubric(render_demand=RenderDemand.FLUENT_DISCOURSE, expected_object="yen",
                          reachable_offline=True, min_sentences=2, min_relations=2,
                          fabrication_traps=("dollar", "euro")),
            expected_frontier="the fact is acquirable (accuracy), but the morning wants multi-sentence, "
                              "register-adapted discourse; the loop emits one grounded template only.",
            named_unlock="fluency register (M-B1/M-B2: fluency realiser wired to CO L3, faithfulness 1.0)",
        ),
    ]


class OAMExaminer:
    """The developer-blind examiner. Holds the holdout capabilities and, per capability, hands out
    ONLY the ``Assignment`` (via :meth:`assignment_for`) and grades ONLY afterward (via the grading
    module, which receives the ``Rubric``)."""

    def __init__(self, capabilities: list[HoldoutCapability] | None = None):
        self.capabilities: list[HoldoutCapability] = list(capabilities or default_holdout())

    def ids(self) -> list[str]:
        return [c.id for c in self.capabilities]

    def by_id(self, cid: str) -> HoldoutCapability:
        return next(c for c in self.capabilities if c.id == cid)

    def assignment_for(self, cid: str) -> Assignment:
        """Hand the loop ONLY the evening study materials — never the rubric."""
        return self.by_id(cid).assignment

    # ── the runtime blindness proof (reported + asserted in the sealed test) ───────────────────
    def blindness_report(self, *, run_capability: Any, rubric_type: type,
                         probe_abstains: dict[str, bool] | None = None) -> dict[str, Any]:
        """Prove blindness at runtime, structurally and empirically. Returns a dict the report and
        the sealed test consume. ``probe_abstains`` maps capability-id -> whether the fresh scratch
        store abstained on the graded question BEFORE the run (supplied by the run module)."""
        # (1) STRUCTURAL: the run entry point takes an Assignment, never a Rubric/HoldoutCapability.
        sig = inspect.signature(run_capability)
        first = next(iter(sig.parameters.values()))
        ann = first.annotation
        ann_name = getattr(ann, "__name__", str(ann))
        run_takes_assignment = ann_name == "Assignment"
        run_never_takes_rubric = all(
            getattr(p.annotation, "__name__", str(p.annotation)) not in ("Rubric", "HoldoutCapability")
            for p in sig.parameters.values())
        rubric_frozen = bool(getattr(rubric_type, "__dataclass_params__", None)
                             and rubric_type.__dataclass_params__.frozen)

        # (2) NO-LEAK: for every capability, the rubric's expected object is NOT in the assignment's
        # world-gap question or topic (the loop is told what to study, not the answer key).
        no_answer_in_question: dict[str, bool] = {}
        for c in self.capabilities:
            obj = (c.rubric.expected_object or "").strip().lower()
            q = (c.assignment.question or "").strip().lower()
            no_answer_in_question[c.id] = (not obj) or (obj not in q)

        # (3) SEED DISJOINTNESS: the invention grading seed differs from the loop's h4 seed.
        seed_disjoint: dict[str, bool] = {}
        for c in self.capabilities:
            if c.faculty in (Faculty.INVENT, Faculty.PERSISTENT):
                seed_disjoint[c.id] = c.rubric.grading_seed != c.assignment.h4_seed

        # (4) WEB below-consensus: the web holdout's fact is carried by < 2 offline domains.
        web_below_consensus: dict[str, bool] = {}
        for c in self.capabilities:
            if c.faculty is Faculty.WEB:
                web_below_consensus[c.id] = (not c.rubric.reachable_offline) \
                    and c.assignment.evidence_domains() < 2

        ok = bool(run_takes_assignment and run_never_takes_rubric and rubric_frozen
                  and all(no_answer_in_question.values())
                  and all(seed_disjoint.values())
                  and all(web_below_consensus.values())
                  and (probe_abstains is None or all(probe_abstains.values())))
        return {
            "blind": ok,
            "run_entry_takes_assignment": run_takes_assignment,
            "run_entry_first_param_type": ann_name,
            "run_never_takes_rubric": run_never_takes_rubric,
            "rubric_is_frozen": rubric_frozen,
            "answer_key_absent_from_question": no_answer_in_question,
            "grading_seed_disjoint_from_loop": seed_disjoint,
            "web_fact_below_offline_consensus": web_below_consensus,
            "pre_run_store_abstains": dict(probe_abstains or {}),
            "note": ("blindness is over the RUBRIC (graded questions + answer key + traps), enforced by "
                     "type: run_capability(Assignment) cannot see a Rubric. Study corpora legitimately "
                     "contain learnable facts; the fresh store abstains before the run, so a correct "
                     "morning answer is genuine overnight acquisition, not a pre-seeded lookup."),
        }
