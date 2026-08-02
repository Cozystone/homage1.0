# -*- coding: utf-8 -*-
"""LIVE adapters that put the contamination firewall on the REAL staging->promotion path.

This is INTEGRATION Pass 2: the pieces `firewall.wiring_pending()` listed as "to be
done in a follow-up that edits the live promotion code". Everything here is either

  * purely ADDITIVE (records provenance/justification metadata without changing any
    gate decision), or
  * gated behind the flag ``ATANOR_MEMBRANE_LIVE`` (default OFF) / an explicit opt-in
    argument, so the DEFAULT behaviour of every shipped path is byte-identical.

What it wires (all default-off)
-------------------------------
1. :class:`FirewallStagePass` -- a STREAMING, O(1)-per-edge pass the stage scripts call
   under ``--firewall``/``ATANOR_MEMBRANE_LIVE`` to attach, per staged edge, the JTMS
   support-list justification, the ATMS environment (= provenance tier), the AGM tier,
   and a provenance record -- plus a *nogood pre-check* that quarantines a staged edge
   contradicting a seeded T0/operator fact. It NEVER opens a TripleStore, NEVER writes
   any store, and NEVER re-ingests -- it observes the (s, p, o) the script already
   produced and emits an out-of-tree JSON manifest.
2. :func:`register_applied_fact` -- the retraction hook
   ``acquisition_daemon.promotion_queue.approve_and_apply`` uses (when handed a firewall)
   so an applied fact is rooted in the firewall's JTMS and a later
   ``ContaminationFirewall.invalidate_source`` flips it (and its dependents) OUT.
3. :func:`tm_record` -- the JTMS/ATMS/tier bundle persisted into the
   ``candidate_promotion_gate`` signed manifest (item 2 of the task).

Scale note (honest): the full JTMS relabels on every node add, so it is O(n^2) to stage
millions of edges into ONE firewall. The stage-script pass therefore does NOT build a
monolithic JTMS -- it builds a fresh 2-node justification per *sampled* edge (O(1)) and
runs the nogood pre-check only against the small seeded T0 set. The monolithic JTMS is
reserved for the SMALL operator-approved apply batch (retraction cascade), where n is
tens--thousands, not tens of millions.

numpy-free; stdlib only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from packages.truth_maintenance.jtms import JTMS
from packages.truth_maintenance.atms import (
    ATMS, T0, CONSENSUS as A_CONSENSUS, SINGLE_SOURCE as A_SINGLE, NEURAL as A_NEURAL,
)
from packages.truth_maintenance.revision import (
    Fact, BeliefBase, OPERATOR, CONSENSUS, SINGLE_SOURCE, NEURAL,
)

# --------------------------------------------------------------------------------------
# the master flag -- default OFF everywhere
# --------------------------------------------------------------------------------------
MEMBRANE_LIVE_FLAG = "ATANOR_MEMBRANE_LIVE"
MEMBRANE_OUT_ENV = "ATANOR_MEMBRANE_OUT"
_TRUTHY = {"1", "true", "yes", "on"}


def membrane_live_enabled(explicit: bool | None = None) -> bool:
    """Is the live membrane turned on? ``explicit`` (a ``--firewall`` flag) wins; else the
    ``ATANOR_MEMBRANE_LIVE`` env var. Default: False."""
    if explicit is not None:
        return bool(explicit)
    return os.environ.get(MEMBRANE_LIVE_FLAG, "").strip().lower() in _TRUTHY


# --------------------------------------------------------------------------------------
# provenance -> epistemic tier policy (S1 Wikidata-truthy lands at single_source; a
# cross-domain consensus overrides to consensus). Tier strings are the AGM/revision names;
# the ATMS assumption for each coincides (operator being the sole rename: operator<->T0).
# --------------------------------------------------------------------------------------
PROVENANCE_TIER: dict[str, str] = {
    "wikidata-truthy": SINGLE_SOURCE,          # one curated source (truthy best-rank)
    "conceptnet-5.7": SINGLE_SOURCE,           # one curated source
    "extracted:rule+topology": NEURAL,         # low-trust regex extraction -> staging only
    "web-consensus": CONSENSUS,                # >= 2 independent domains
}
DEFAULT_TIER = SINGLE_SOURCE

_TIER_ASSUMPTION = {OPERATOR: T0, CONSENSUS: A_CONSENSUS,
                    SINGLE_SOURCE: A_SINGLE, NEURAL: A_NEURAL}


def tier_for_provenance(provenance: str, *, consensus_domains: int = 0,
                        k_consensus: int = 2) -> str:
    """Map a provenance tag to its AGM tier. A candidate reaching ``k_consensus``
    independent domains is lifted to ``consensus`` regardless of its base tag."""
    if consensus_domains >= k_consensus:
        return CONSENSUS
    return PROVENANCE_TIER.get(provenance, DEFAULT_TIER)


def tier_assumption(tier: str) -> str:
    """The ATMS assumption name for an AGM tier."""
    return _TIER_ASSUMPTION.get(tier, A_SINGLE)


def fact_key(subject: str, predicate: str, object: str) -> str:
    """The firewall's canonical datum key (matches ContaminationFirewall.stage_candidate)."""
    return f"{predicate}({subject})={object}"


# --------------------------------------------------------------------------------------
# faithful per-edge justification (a fresh 2-node JTMS -> O(1); scales to millions)
# --------------------------------------------------------------------------------------
def one_justification(subject: str, predicate: str, object: str, *,
                      provenance: str, source_id: str) -> dict:
    """The Doyle SL-justification for one staged edge, as a real JTMS would label it:
    a source premise supports the fact. O(1): the JTMS holds exactly two nodes."""
    key = fact_key(subject, predicate, object)
    j = JTMS()
    j.add_premise(source_id, informant=provenance)
    j.add_justified(key, support=[source_id], informant=provenance)
    return j.explanation(key)


def tm_record(firewall: Any, key: str, tier: str) -> dict:
    """The JTMS/ATMS/tier provenance bundle persisted alongside a promotion (task item 2).
    Identical shape to RealPromotionGateAdapter.confirm_batch's per-item block."""
    return {
        "jtms_justification": firewall.jtms.explanation(key),
        "atms_env": sorted(sorted(e) for e in firewall.atms.label(key)),
        "atms_invalidated": firewall.atms.invalidated(key),
        "tier": tier,
    }


# --------------------------------------------------------------------------------------
# 1) the STREAMING stage pass the scripts call (observe-only; store contents unchanged)
# --------------------------------------------------------------------------------------
@dataclass
class FirewallStagePass:
    """A streaming, default-off membrane over a stage script's edge loop.

    Call :meth:`observe` once per edge the script stages (right after ``store.add``
    succeeds). It attaches provenance/justification metadata and, if T0/operator facts
    were seeded, runs the nogood pre-check: an edge whose ``(subject, predicate)`` clashes
    with a seeded functional T0 fact is recorded as an ATMS nogood, listed in
    :attr:`quarantined`, and reported by ``observe`` as *not passed*. The pass is
    OBSERVE-ONLY: it does not, and cannot, change what the script wrote to the store --
    the quarantine is advisory metadata the operator/promotion gate consumes.
    """

    provenance: str
    t0_facts: Sequence[tuple[str, str, str]] = ()
    k_consensus: int = 2
    sample_cap: int = 50

    tier: str = field(init=False)
    _assumption: str = field(init=False)
    _source_id: str = field(init=False)
    _bb: BeliefBase | None = field(init=False, default=None)
    _atms: ATMS | None = field(init=False, default=None)
    observed: int = field(init=False, default=0)
    passed: int = field(init=False, default=0)
    quarantined: list[dict] = field(init=False, default_factory=list)
    nogoods: list[list[str]] = field(init=False, default_factory=list)
    sample_records: list[dict] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.tier = PROVENANCE_TIER.get(self.provenance, DEFAULT_TIER)
        self._assumption = tier_assumption(self.tier)
        self._source_id = f"src:{self.provenance}"
        if self.t0_facts:
            # tiny belief base of ONLY the operator facts -> conflicts_with() is O(t0)
            self._bb = BeliefBase(facts=[Fact(s, p, o, OPERATOR) for (s, p, o) in self.t0_facts])
            self._atms = ATMS(core=(T0,))
            for (s, p, o) in self.t0_facts:
                self._atms.assume(fact_key(s, p, o), {T0})

    # -- one staged edge --------------------------------------------------------
    def observe(self, subject: str, predicate: str, object: str, *,
                consensus_domains: int = 0) -> bool:
        """Route one staged edge through the membrane. Returns True if it passes, False if
        it is quarantined by the nogood pre-check. O(1) unless T0 facts were seeded."""
        self.observed += 1
        key = fact_key(subject, predicate, object)
        edge_tier = tier_for_provenance(self.provenance, consensus_domains=consensus_domains,
                                        k_consensus=self.k_consensus)

        if self._bb is not None:
            conflicts = self._bb.conflicts_with(Fact(subject, predicate, object, edge_tier))
            if conflicts:
                self._atms.assume(key, {tier_assumption(edge_tier)})  # type: ignore[union-attr]
                clash_keys = []
                for c in conflicts:
                    ck = fact_key(c.subject, c.predicate, c.object)
                    for ng in self._atms.register_contradiction(key, ck):  # type: ignore[union-attr]
                        self.nogoods.append(sorted(ng))
                    clash_keys.append(ck)
                self.quarantined.append({
                    "fact_key": key,
                    "subject": subject, "predicate": predicate, "object": object,
                    "contradicts": clash_keys,
                    "atms_invalidated": self._atms.invalidated(key),  # type: ignore[union-attr]
                    "reason": "nogood_contradicts_T0_operator_fact",
                })
                return False

        self.passed += 1
        if len(self.sample_records) < self.sample_cap:
            self.sample_records.append({
                "fact_key": key,
                "jtms_justification": one_justification(
                    subject, predicate, object,
                    provenance=self.provenance, source_id=self._source_id),
                "atms_env": [[self._assumption]],
                "tier": edge_tier,
                "provenance": self.provenance,
            })
        return True

    # -- final manifest ---------------------------------------------------------
    def manifest(self) -> dict:
        """The out-of-tree provenance/nogood manifest (JSON-able). Bounded size:
        counts + all quarantined edges + all nogoods + a capped sample of justifications."""
        return {
            "membrane_live": True,
            "flag": MEMBRANE_LIVE_FLAG,
            "provenance": self.provenance,
            "tier": self.tier,
            "atms_env": [self._assumption],
            "k_consensus": self.k_consensus,
            "t0_facts_seeded": [list(f) for f in self.t0_facts],
            "observed": self.observed,
            "passed": self.passed,
            "quarantined_count": len(self.quarantined),
            "quarantined": self.quarantined,
            "nogoods": self.nogoods,
            "sample_record_count": len(self.sample_records),
            "sample_records": self.sample_records,
            "production_store_mutated": False,
            "note": ("observe-only provenance + nogood layer; the stage store's contents are "
                     "unchanged and the shipped store is never opened. Quarantine is advisory "
                     "metadata for the operator-signed promotion gate."),
        }


def stage_edges_through_firewall(
    edges: Iterable[Sequence[str]], *, provenance: str,
    t0_facts: Sequence[tuple[str, str, str]] = (), k_consensus: int = 2,
    sample_cap: int = 1000,
) -> FirewallStagePass:
    """Batch convenience over :class:`FirewallStagePass`: route an iterable of ``(subject,
    predicate, object[, consensus_domains])`` tuples through the membrane and return the
    finished pass (``.passed``/``.quarantined``/``.nogoods``/``.manifest()``). Metadata
    only -- never opens or writes any store."""
    fp = FirewallStagePass(provenance=provenance, t0_facts=t0_facts,
                           k_consensus=k_consensus, sample_cap=sample_cap)
    for edge in edges:
        s, p, o = edge[0], edge[1], edge[2]
        cd = int(edge[3]) if len(edge) > 3 else 0
        fp.observe(s, p, o, consensus_domains=cd)
    return fp


# --------------------------------------------------------------------------------------
# out-of-tree manifest writer (never data/graph_scale, never the shipped store)
# --------------------------------------------------------------------------------------
_FORBIDDEN_OUT = ("data/graph_scale", "kg_triples")


def default_firewall_out(name: str) -> Path:
    """Where a stage script drops its firewall manifest. NEVER under data/graph_scale --
    defaults to ``runtime/firewall/<name>_firewall_manifest.json`` (or ``ATANOR_MEMBRANE_OUT``)."""
    base = os.environ.get(MEMBRANE_OUT_ENV)
    if base:
        return Path(base)
    return Path("runtime") / "firewall" / f"{name}_firewall_manifest.json"


def write_manifest(stage_pass: FirewallStagePass, out: Path | str) -> Path:
    """Write ``stage_pass.manifest()`` to ``out`` (JSON). Refuses any path under
    data/graph_scale or a shipped-store marker -- the membrane never co-writes the ingest tree."""
    import json
    p = Path(out)
    norm = str(p).replace("\\", "/").lower()
    if any(marker in norm for marker in _FORBIDDEN_OUT):
        raise PermissionError(
            f"refused: firewall manifest out path {p} is under the ingest/shipped tree; "
            f"the membrane writes only out-of-tree (e.g. runtime/firewall/)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stage_pass.manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def stage_pass_if_enabled(provenance: str, *, enabled: bool | None = None,
                          t0_facts: Sequence[tuple[str, str, str]] = (),
                          sample_cap: int = 50) -> FirewallStagePass | None:
    """Return a :class:`FirewallStagePass` iff the membrane is live (``--firewall`` flag or
    ``ATANOR_MEMBRANE_LIVE``), else None. The scripts guard every membrane call on the
    return being non-None, so default (flag off) is a byte-identical no-op."""
    if not membrane_live_enabled(enabled):
        return None
    return FirewallStagePass(provenance=provenance, t0_facts=t0_facts, sample_cap=sample_cap)


# --------------------------------------------------------------------------------------
# 2/3) the promotion-path helpers (retraction hook + manifest persistence)
# --------------------------------------------------------------------------------------
def register_applied_fact(firewall: Any, subject: str, predicate: str, object: str, *,
                          provenance: str, source_id: str,
                          consensus_domains: int = 0, operator_signed: bool = False) -> dict:
    """Root an applied fact in ``firewall``'s JTMS/ATMS/AGM so a later
    ``firewall.invalidate_source(source_id)`` flips it (and its dependents) OUT.

    Used by ``approve_and_apply`` when a firewall is supplied (default-off). Promotes at
    the fact's consensus tier (or operator, if signed) so the JTMS justification is IN and
    dependency-directed retraction is available."""
    rec = firewall.stage_candidate(subject, predicate, object,
                                   provenance=provenance, source_id=source_id)
    domains = consensus_domains if consensus_domains else firewall.k_consensus
    out = firewall.promote(rec, operator_signed=operator_signed, consensus_domains=domains)
    return {"fact_key": rec.fact_key, "source_id": source_id, "tier": rec.tier, "promote": out}


def wiring_live() -> list[str]:
    """What ``ATANOR_MEMBRANE_LIVE`` / the opt-in arguments now wire onto the REAL path
    (the complement of ``firewall.wiring_pending``). Honest: all default-off."""
    return [
        "stage scripts (--firewall / ATANOR_MEMBRANE_LIVE): FirewallStagePass.observe attaches "
        "per-edge JTMS justification + ATMS env(tier) + AGM tier + provenance, and nogood-"
        "quarantines edges contradicting a seeded T0 fact; observe-only, manifest written "
        "out-of-tree (runtime/firewall), the stage store is unchanged.",
        "candidate_promotion_gate.confirm_promotion(truth_maintenance=...): persists the JTMS "
        "justification + ATMS env + tier per item into the SIGNED manifest (decision unchanged; "
        "default None -> manifest byte-identical).",
        "acquisition_daemon.promotion_queue.approve_and_apply(firewall=...): registers each "
        "applied fact in the firewall JTMS (register_applied_fact) so invalidate_source later "
        "flips it OUT; default firewall=None -> unchanged.",
        "nogood pre-check (FirewallStagePass with t0_facts, or approve_and_apply firewall path): "
        "a staged edge contradicting a T0/operator fact is recorded as an ATMS nogood and "
        "excluded; default (no seed / no firewall) promotes exactly today's set.",
    ]
