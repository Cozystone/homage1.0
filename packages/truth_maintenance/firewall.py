# -*- coding: utf-8 -*-
"""The contamination firewall: staged, default-deny promotion pipeline.

This ties JTMS + ATMS + AGM + defeasible reasoning into the six-stage firewall of
docs/ATANOR_final_gate_research.md §2 (NS-3), and adapts onto ATANOR's REAL,
already-shipped operator-signed promotion gate.

Pipeline (default-deny at every stage)
--------------------------------------
    candidate
      -> stage 1  ATMS quarantine: datum assumed only under {neural}
      -> stage 2  verification battery (PLUGGABLE; conformal_gate is the plug --
                  referenced, NOT re-implemented here)
      -> stage 3  AGM tier assignment (entrenchment = operator>consensus>single>neural)
      -> stage 4  promotion ONLY on operator-sign OR k-source consensus
                  (records the JTMS justification + lifts the ATMS environment)
      -> stage 5  JTMS dependency-directed retraction on source invalidation

It **never writes the shipped store**. Promotion-to-shipped is the operator-signed
morning step (`candidate_promotion_gate`); this layer STAGES and RECORDS, and the
:class:`RealPromotionGateAdapter` shows how a firewall batch is handed to that real
gate (demonstrated on a scratch staging dir in the tests).

What is wired vs wiring-pending (honest, like M1)
-------------------------------------------------
Wired here:
  * the four formalisms and their unit behaviours (see tests);
  * the adapter that converts firewall records into the exact item dicts
    ``candidate_promotion_gate.CandidatePromotionGate.confirm_promotion`` expects,
    and calls it on a scratch staging dir.
Wiring-pending (see :func:`wiring_pending`), to be done in a follow-up that edits
the live promotion code (out of scope for this task, which builds the layer only):
  * the real gate stores no JTMS justification / ATMS env / nogood ledger on its
    manifest yet -- the adapter attaches them alongside, but persisting them into
    the manifest schema is a change to `candidate_promotion_gate`;
  * `acquisition_daemon.promotion_queue.approve_and_apply` should call
    :meth:`ContaminationFirewall.invalidate_source` when a source is later
    retracted, so applied facts flip OUT;
  * stage-2 should call the real `conformal_gate.ConformalGate` as the battery.

No numpy; stdlib only. Never opens any TripleStore itself; the adapter's optional
end-to-end demo writes only to a caller-supplied scratch store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from packages.truth_maintenance import atms as _atms
from packages.truth_maintenance.atms import ATMS, T0, CONSENSUS, SINGLE_SOURCE, NEURAL
from packages.truth_maintenance.jtms import JTMS
from packages.truth_maintenance.revision import (
    BeliefBase, Fact, OPERATOR, CONSENSUS as R_CONSENSUS,
    SINGLE_SOURCE as R_SINGLE, NEURAL as R_NEURAL,
)
from packages.truth_maintenance.defeasible import DefeasibleReasoner, WITHDRAWN


# ---------------------------------------------------------------------------
# Stage 2: the pluggable verification battery (conformal_gate is the plug)
# ---------------------------------------------------------------------------
@dataclass
class VerificationOutcome:
    verified: bool
    method: str
    detail: dict = field(default_factory=dict)


class VerificationBattery(Protocol):
    """Pluggable interface for stage 2. `conformal_gate.ConformalGate.decide`
    (which returns a `GateDecision` with `.accept`) is the intended implementation
    -- referenced, never re-implemented here."""

    def verify(self, fact: dict, signals: Any = None) -> VerificationOutcome: ...


class AbstainingBattery:
    """Default-deny battery: verifies nothing (abstains) unless a real battery is
    supplied. Makes "no verifier wired" fail safe."""

    def verify(self, fact: dict, signals: Any = None) -> VerificationOutcome:
        return VerificationOutcome(False, "abstain_no_battery",
                                   {"reason": "no verification battery wired -> default-deny"})


class ConformalBattery:
    """Adapter that plugs a `conformal_gate.ConformalGate` (or anything with a
    ``decide(signals) -> obj.accept``) in as the stage-2 battery. Duck-typed so
    :mod:`truth_maintenance` never imports conformal_gate at module load.
    """

    def __init__(self, gate: Any) -> None:
        self._gate = gate

    def verify(self, fact: dict, signals: Any = None) -> VerificationOutcome:
        decision = self._gate.decide(signals)
        accept = bool(getattr(decision, "accept", False))
        return VerificationOutcome(
            accept, "conformal_gate",
            {"nonconformity": getattr(decision, "nonconformity", None),
             "q_hat": getattr(decision, "q_hat", None),
             "certificate": getattr(decision, "certificate", {})},
        )


# ---------------------------------------------------------------------------
# Firewall records
# ---------------------------------------------------------------------------
_TIER_TO_ENV = {OPERATOR: T0, R_CONSENSUS: CONSENSUS, R_SINGLE: SINGLE_SOURCE, R_NEURAL: NEURAL}


@dataclass
class StagedRecord:
    subject: str
    predicate: str
    object: str
    provenance: str
    source_id: str
    fact_key: str
    status: str = "staged"                 # staged -> promoted | rejected | retracted
    tier: str = R_NEURAL
    verification: VerificationOutcome | None = None
    reason: str = ""

    def as_fact(self) -> Fact:
        return Fact(self.subject, self.predicate, self.object, self.tier)


# the shipped store we must never write (guard)
SHIPPED_STORE_MARKERS = ("kg_triples",)


def _is_shipped_store(root: Path | str) -> bool:
    p = str(Path(root)).replace("\\", "/").lower()
    return any(m in p for m in SHIPPED_STORE_MARKERS)


class ContaminationFirewall:
    """Default-deny staging + belief-management layer.

    Stages candidates into ATMS ``{neural}`` quarantine, records JTMS
    justifications, and promotes only on operator-sign or consensus -- resolving
    conflicts by AGM entrenchment and retracting dependents on source
    invalidation. Never writes the shipped store.
    """

    def __init__(
        self,
        *,
        battery: VerificationBattery | None = None,
        k_consensus: int = 2,
    ) -> None:
        self.atms = ATMS(core=(T0,))
        self.jtms = JTMS()
        self.beliefs = BeliefBase()
        self.defeasible = DefeasibleReasoner(jtms=self.jtms)
        self.battery: VerificationBattery = battery or AbstainingBattery()
        self.k_consensus = k_consensus
        self.records: dict[str, StagedRecord] = {}

    # ---- stage 1: quarantine --------------------------------------------------
    def stage_candidate(
        self, subject: str, predicate: str, object: str, *,
        provenance: str, source_id: str,
    ) -> StagedRecord:
        """Admit a candidate into ATMS ``{neural}`` quarantine + a JTMS
        justification rooted at its source. Default-deny: nothing is believed as
        promoted knowledge yet."""
        fact_key = f"{predicate}({subject})={object}"
        rec = StagedRecord(subject, predicate, object, provenance, source_id, fact_key)
        # ATMS: hold only under the neural assumption (quarantine staging)
        self.atms.assume(fact_key, {NEURAL})
        # JTMS: source premise -> fact justified by the source
        self.jtms.add_premise(source_id, informant=provenance)
        self.jtms.add_justified(fact_key, support=[source_id], informant=provenance)
        self.records[fact_key] = rec
        return rec

    # ---- stage 2: verification ------------------------------------------------
    def verify(self, rec: StagedRecord, signals: Any = None) -> VerificationOutcome:
        outcome = self.battery.verify(
            {"subject": rec.subject, "predicate": rec.predicate, "object": rec.object},
            signals,
        )
        rec.verification = outcome
        return outcome

    # ---- stage 3+4: tier assignment + promotion (default-deny) ----------------
    def promote(
        self, rec: StagedRecord, *,
        operator_signed: bool = False,
        consensus_domains: int = 0,
        require_verification: bool = False,
    ) -> dict:
        """Promote a staged record -- ONLY on operator-sign or k-source consensus.

        On success: assign the AGM tier, run AGM revision into the belief base
        (drops least-entrenched conflicts, never the operator core), lift the
        ATMS environment out of quarantine, and re-record the JTMS justification
        with the verification informant. Never writes the shipped store.
        """
        if rec.fact_key not in self.records:
            return {"promoted": False, "reason": "not_staged"}

        if require_verification and not (rec.verification and rec.verification.verified):
            rec.status, rec.reason = "rejected", "verification_not_passed"
            return {"promoted": False, "reason": rec.reason}

        # default-deny gate
        if operator_signed:
            tier = OPERATOR
        elif consensus_domains >= self.k_consensus:
            tier = R_CONSENSUS
        else:
            rec.status = "staged"
            rec.reason = "default_deny_no_operator_no_consensus"
            return {"promoted": False, "reason": rec.reason,
                    "note": "stays in {neural} quarantine"}

        rec.tier = tier
        # AGM revision: resolve conflicts by entrenchment (never drop operator)
        result = self.beliefs.promote(rec.as_fact())
        if not result.accepted:
            rec.status, rec.reason = "rejected", result.rejected_reason
            return {"promoted": False, "reason": result.rejected_reason,
                    "agm": _agm_summary(result)}

        # lift ATMS environment out of quarantine to the assigned tier
        self.atms.assume(rec.fact_key, {_TIER_TO_ENV[tier]})
        # re-record JTMS justification with the verification/tier informant
        vinf = f"verified:{tier}"
        self.jtms.add_justified(rec.fact_key, support=[rec.source_id], informant=vinf)
        rec.status, rec.reason = "promoted", "operator_signed" if operator_signed else "consensus"
        return {
            "promoted": True,
            "tier": tier,
            "reason": rec.reason,
            "jtms_justification": self.jtms.explanation(rec.fact_key),
            "atms_env": sorted(sorted(e) for e in self.atms.label(rec.fact_key)),
            "agm": _agm_summary(result),
            "production_store_mutated": False,
        }

    # ---- stage 5: retraction on source invalidation ---------------------------
    def invalidate_source(self, source_id: str) -> dict:
        """A source was invalidated: retract its JTMS **premise node**.

        ``source_id`` is the source premise every fact staged from it depends on
        (inlist). Retracting that premise triggers dependency-directed retraction
        -- every belief resting on the source (and its descendants) flips OUT
        with no separate sweep. Returns the fact keys that flipped OUT."""
        before = set(self.jtms.beliefs())
        self.jtms.retract(source_id)                 # withdraw the source premise
        after = set(self.jtms.beliefs())
        flipped = sorted(before - after)
        # reflect into records + AGM base
        for key in flipped:
            rec = self.records.get(key)
            if rec is not None:
                rec.status = "retracted"
                self.beliefs.contract(rec.as_fact())
        return {"invalidated_source": source_id, "flipped_out": flipped}

    # ---- M3 blind-spot path: graph-encoded inheritance exceptions -------------
    def register_inheritance_default(self, instance: str, cls: str, prop: str) -> str:
        """Encode an inherited default (``instance is_a cls`` & ``cls`` has
        ``prop`` ~> ``instance`` has ``prop``)."""
        return self.defeasible.add_inheritance_default(instance, cls, prop)

    def register_exception(self, instance: str, prop: str, *, marker: str | None = None) -> dict:
        """A graph-encoded exception undercuts an inherited default -- withdraws
        its warrant WITHOUT asserting the negation (M3 blind-spot closure for
        graph-encodable exceptions). Returns the new status."""
        conclusion = f"{prop}({instance})"
        self.defeasible.add_exception(instance, prop, marker=marker)
        return {
            "conclusion": conclusion,
            "status": self.defeasible.status(conclusion),   # WITHDRAWN
            "asserted_negations": sorted(self.defeasible.asserted_negations()),  # []
        }

    # ---- queries / guards -----------------------------------------------------
    def promoted_facts(self) -> list[Fact]:
        return self.beliefs.facts()

    def safe_context(self) -> list[str]:
        """Data holding under the operator core only (safe mode)."""
        return self.atms.context({T0})

    def creative_context(self) -> list[str]:
        """Data holding under operator core + neural (creative mode)."""
        return self.atms.context({T0, NEURAL})

    @staticmethod
    def assert_not_shipped(root: Path | str) -> None:
        """Hard guard: refuse to target the shipped store."""
        if _is_shipped_store(root):
            raise PermissionError(
                f"refused: {root} looks like the shipped kg_triples store; the "
                f"firewall never writes it (promotion is the operator morning step)"
            )


def _agm_summary(result) -> dict:
    return {
        "accepted": result.accepted,
        "dropped": [f"{f.predicate}({f.subject})={f.object}@{f.tier}" for f in result.dropped],
        "rejected_reason": result.rejected_reason,
    }


# ---------------------------------------------------------------------------
# Adapter onto the REAL operator-signed promotion gate (read-only wrap)
# ---------------------------------------------------------------------------
class RealPromotionGateAdapter:
    """Wraps `candidate_promotion_gate.CandidatePromotionGate` -- ATANOR's real,
    shipped, operator-signed staging gate -- so a firewall batch can flow through
    the *existing* default-deny signature path unchanged.

    It does not modify the live gate. It converts firewall records into the exact
    item dicts the gate expects, calls the real `confirm_promotion` on a scratch
    staging dir, and attaches the firewall's JTMS justification + ATMS env to each
    signed item (persisting those into the manifest schema is wiring-pending).
    """

    def __init__(self, firewall: ContaminationFirewall, *, staging_dir: Path | str) -> None:
        ContaminationFirewall.assert_not_shipped(staging_dir)
        self.firewall = firewall
        self.staging_dir = Path(staging_dir)

    @staticmethod
    def record_to_gate_item(rec: StagedRecord, *, confidence: float, source_refs: list[str]) -> dict:
        """Build the review-queue item dict `CandidatePromotionGate` scores.
        Mirrors `acquisition_daemon.promotion_queue.result_to_item` shape."""
        import hashlib
        digest = hashlib.sha256(rec.fact_key.encode("utf-8")).hexdigest()[:16]
        return {
            "item_id": f"cloud_candidate_{digest}",
            "item_type": "cloud_candidate",
            "title": f"{rec.subject} {rec.predicate} = {rec.object}",
            "summary": (f"Firewall-staged relational fact {rec.subject} {rec.predicate} "
                        f"{rec.object}; provenance {rec.provenance}."),
            "source_refs": list(source_refs),
            "risk_level": "low",
            "confidence": round(float(confidence), 4),
            "status": "approved",     # the operator's per-item review decision
            "fact": {"subject": rec.subject, "predicate": rec.predicate, "object": rec.object},
        }

    def confirm_batch(
        self, records: list[StagedRecord], *,
        operator_confirmed: bool,
        confirmation_phrase: str,
        operator_id: str = "operator",
        confidence: float = 0.8,
        source_refs: list[str] | None = None,
    ) -> dict:
        """Hand a firewall batch to the REAL gate's `confirm_promotion` (default-
        deny + exact phrase). Returns the gate's signed manifest, augmented with
        the firewall's JTMS/ATMS records per item. Writes only the scratch dir."""
        # lazy, read-only import of the shipped gate
        from packages.candidate_promotion_gate import CandidatePromotionGate

        refs = source_refs or ["firewall://staged"]
        items = [self.record_to_gate_item(r, confidence=confidence, source_refs=refs)
                 for r in records]
        gate = CandidatePromotionGate(staging_dir=self.staging_dir)
        # firewall belief-management provenance -- now PERSISTED into the signed manifest
        # (task item 2): built BEFORE the gate call and handed to confirm_promotion so it
        # lands in the written artifact, not merely on the returned dict.
        truth_maintenance = {
            r.fact_key: {
                "jtms_justification": self.firewall.jtms.explanation(r.fact_key),
                "atms_env": sorted(sorted(e) for e in self.firewall.atms.label(r.fact_key)),
                "atms_invalidated": self.firewall.atms.invalidated(r.fact_key),
                "tier": r.tier,
            }
            for r in records
        }
        signed = gate.confirm_promotion(
            items, item_ids=[it["item_id"] for it in items],
            operator_confirmed=operator_confirmed,
            confirmation_phrase=confirmation_phrase, operator_id=operator_id,
            truth_maintenance=truth_maintenance,
        )
        # keep it visible on the returned dict even on a denial (nothing was persisted then)
        signed.setdefault("truth_maintenance", truth_maintenance)
        return signed


def wiring_pending() -> list[str]:
    """What still must be wired into the LIVE DEFAULT promotion path.

    Pass 2 landed the flag-gated / opt-in live adapters (see
    :func:`packages.truth_maintenance.live_membrane.wiring_live`); the items below are the
    honest remainder -- either the flag-OFF default still lacks them, or they are
    deliberately out of scope for Pass 2.
    """
    return [
        "candidate_promotion_gate: confirm_promotion now PERSISTS the JTMS justification + "
        "ATMS environment + tier per item when handed truth_maintenance=... (task item 2, "
        "DONE, additive/default-None). Still pending: a manifest schema-version bump and a "
        "dedicated nogood-ledger field on the manifest.",
        "acquisition_daemon.promotion_queue.approve_and_apply: registers each applied fact "
        "in the firewall JTMS when firewall=... is passed, so ContaminationFirewall."
        "invalidate_source flips it (and its dependents) OUT (task item 3, DONE behind the "
        "opt-in). Pending: the DEFAULT firewall=None path still does not call "
        "invalidate_source -- retraction is opt-in, never automatic.",
        "firewall stage 2: replace AbstainingBattery with ConformalBattery wrapping the real "
        "conformal_gate.ConformalGate calibrated on the sealed QA set (out of scope for Pass "
        "2 -- conformal_gate is owned by Pass 1 and must not be touched here).",
        "scripts/stage_r2_conceptnet + wikidata_truthy_ingest: route staged edges through "
        "FirewallStagePass under --firewall / ATANOR_MEMBRANE_LIVE (task item 1, DONE, "
        "default off, observe-only). Pending: seeding the operator T0 set into the scripts so "
        "the nogood pre-check also fires during staging, not only at the promotion gate.",
    ]
