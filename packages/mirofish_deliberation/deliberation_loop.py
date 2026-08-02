"""MiroFish REAL multi-step deliberation loop.

The single-pass simulator (simulator.py) fires every role once over caller-supplied
strings. This loop is the real thing the roadmap asked for, built structurally — not
staged dialog:

  1. GROUNDED: role findings come from live reads of the consensus-evidence ledger
     (voices, quarantine, promoted keys) — the same files the learning pipeline writes.
  2. MULTI-STEP: a blocking objection raised in round N triggers a RESOLUTION PROBE in
     round N+1 — another real read that either resolves the objection (with the observed
     data cited in the transcript) or leaves it standing. State evolves between rounds.
  3. FIXED POINT: the loop stops when a round changes nothing, or at max_rounds.

Honesty contract (inherited from the lab doc): read-only, review-only. No external LLM,
no production mutation, no Local Brain write, no candidate promotion, no real P2P. The
final recommendation always requires explicit human approval.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

Recommendation = str  # "approve_for_review" | "needs_more_evidence" | "blocked"


@dataclass(frozen=True)
class LoopStatement:
    """One role's contribution in one round, with the real data it observed."""

    round_no: int
    role: str
    stance: str
    findings: list[str]
    blocks_promotion: bool = False
    probe: str | None = None            # which real read produced this (round > 1)
    observed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Objection:
    kind: str          # insufficient_evidence | contradictions_on_record | thin_topic | privacy | route_blocked
    raised_by: str
    detail: str
    blocking: bool
    resolvable: bool   # False → only a human can clear it (privacy, router)


@dataclass
class LoopResult:
    topic: str
    rounds_run: int
    fixed_point: bool
    transcript: list[LoopStatement] = field(default_factory=list)
    objections_open: list[dict[str, Any]] = field(default_factory=list)
    objections_resolved: list[dict[str, Any]] = field(default_factory=list)
    synthesis: str = ""
    promotion_recommendation: Recommendation = "blocked"
    requires_manual_approval: bool = True
    production_store_mutated: bool = False
    local_brain_write: bool = False
    external_llm_used: bool = False
    real_p2p_used: bool = False
    candidate_promotion: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["transcript"] = [s.to_dict() for s in self.transcript]
        return payload


def _read_quarantine(root: Path, topic: str) -> list[dict[str, Any]]:
    """Curated-judge quarantine records whose canonical key involves the topic."""
    path = root / "curated_quarantine.jsonl"
    if not path.exists():
        return []
    topic_l = topic.strip().lower()
    hits: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if topic_l and topic_l in str(rec.get("key") or "").lower():
            hits.append(rec)
    return hits


def _promoted_keys(root: Path) -> set[str]:
    path = root / "promoted_keys.jsonl"
    keys: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                keys.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                continue
    return keys


def run_deliberation_loop(
    topic: str,
    *,
    ledger_root: str | Path,
    privacy_report: dict[str, Any] | None = None,
    router_report: dict[str, Any] | None = None,
    max_rounds: int = 3,
) -> LoopResult:
    """Run the grounded multi-round chamber over REAL ledger state. Read-only."""
    if not topic:
        raise ValueError("topic is required")
    from packages.cloud_brain.consensus_ledger import ConsensusLedger

    root = Path(ledger_root)
    ledger = ConsensusLedger(root)
    privacy_report = privacy_report or {}
    router_report = router_report or {}

    transcript: list[LoopStatement] = []
    open_objs: list[Objection] = []
    resolved: list[dict[str, Any]] = []

    # ---- round 1: every role reads real state once -------------------------------
    ev = ledger.evidence_for_label(topic)
    quarantined = _read_quarantine(root, topic)

    transcript.append(LoopStatement(
        1, "builder", "construct",
        [f"{ev['distinct_relations']} ledger relations / max {ev['max_voices']} voices for '{topic}'"],
        blocks_promotion=ev["distinct_relations"] == 0, observed=ev))
    if ev["distinct_relations"] == 0:
        open_objs.append(Objection("thin_topic", "builder",
                                   "no ledger relations at all for this topic", True, True))

    if ev["max_voices"] < ev["min_sources_required"]:
        detail = (f"strongest relation has {ev['max_voices']} voice(s); "
                  f"consensus needs {ev['min_sources_required']}")
        open_objs.append(Objection("insufficient_evidence", "skeptic", detail, True, True))
        transcript.append(LoopStatement(1, "skeptic", "challenge", [detail], blocks_promotion=True))
    else:
        transcript.append(LoopStatement(
            1, "skeptic", "challenge",
            [f"consensus threshold met ({ev['max_voices']}/{ev['min_sources_required']} voices)"]))

    if quarantined:
        detail = f"{len(quarantined)} curated-judge contradiction(s) on record for this topic"
        open_objs.append(Objection("contradictions_on_record", "domain_expert", detail, True, True))
        transcript.append(LoopStatement(
            1, "domain_expert", "scope", [detail], blocks_promotion=True,
            observed={"quarantined": quarantined[:5]}))
    else:
        transcript.append(LoopStatement(
            1, "domain_expert", "scope", ["no curated-judge contradiction on record"]))

    privacy_hit = any(bool(privacy_report.get(f)) for f in
                      ("private_data_present", "raw_private_data", "contains_secret"))
    if privacy_hit:
        open_objs.append(Objection("privacy", "privacy_guard",
                                   "private raw data flagged — only a human can clear this", True, False))
    transcript.append(LoopStatement(
        1, "privacy_guard", "guard",
        ["private raw data flagged"] if privacy_hit else ["no private-data flag present"],
        blocks_promotion=privacy_hit))

    route_allowed = bool(router_report.get("route_allowed", True))
    if not route_allowed:
        open_objs.append(Objection("route_blocked", "router",
                                   "router blocks this route", True, False))
    transcript.append(LoopStatement(
        1, "router", "route",
        ["router allows local review"] if route_allowed else ["router blocks this route"],
        blocks_promotion=not route_allowed))

    # ---- rounds 2..N: resolution probes over still-open objections ----------------
    rounds_run = 1
    fixed_point = False
    while rounds_run < max_rounds and open_objs:
        rounds_run += 1
        changed = False
        still_open: list[Objection] = []
        for obj in open_objs:
            if not obj.resolvable:
                still_open.append(obj)
                continue
            if obj.kind in ("insufficient_evidence", "thin_topic"):
                # probe: RE-READ the ledger FROM DISK (a fresh instance re-loads the
                # jsonl, so evidence landed since round 1 — or old evidence merged by a
                # newly learned alias — is seen). Resolve only on what the file now says.
                probe_ev = ConsensusLedger(root).evidence_for_label(topic)
                ok = (probe_ev["max_voices"] >= probe_ev["min_sources_required"]
                      if obj.kind == "insufficient_evidence"
                      else probe_ev["distinct_relations"] > 0)
                transcript.append(LoopStatement(
                    rounds_run, "skeptic" if obj.kind == "insufficient_evidence" else "builder",
                    "re-examine",
                    [f"probe re-read ledger: {probe_ev['distinct_relations']} relations, "
                     f"max {probe_ev['max_voices']} voices"],
                    blocks_promotion=not ok, probe="consensus_ledger.evidence_for_label",
                    observed=probe_ev))
                if ok:
                    resolved.append({**asdict(obj), "resolved_round": rounds_run,
                                     "resolution": "ledger evidence now meets the bar"})
                    changed = True
                else:
                    still_open.append(obj)
            elif obj.kind == "contradictions_on_record":
                # probe: are ALL contradicted keys isolated (none promoted)? If the
                # quarantine held, the system already contained the damage — the
                # objection resolves WITH that proof; any promoted contradiction stands.
                promoted = _promoted_keys(root)
                leaked = [q for q in _read_quarantine(root, topic) if q.get("key") in promoted]
                transcript.append(LoopStatement(
                    rounds_run, "domain_expert", "verify-isolation",
                    [f"{len(leaked)} contradicted key(s) leaked into promotion"
                     if leaked else "all contradicted keys isolated in quarantine, none promoted"],
                    blocks_promotion=bool(leaked), probe="promoted_keys ∩ curated_quarantine",
                    observed={"leaked": leaked[:5]}))
                if leaked:
                    still_open.append(obj)
                else:
                    resolved.append({**asdict(obj), "resolved_round": rounds_run,
                                     "resolution": "contradictions verified isolated"})
                    changed = True
            else:  # pragma: no cover — future kinds stay open by default
                still_open.append(obj)
        open_objs = still_open
        if not changed:
            fixed_point = True
            break
    if not open_objs:
        fixed_point = True

    # ---- synthesis + judge over the FINAL state -----------------------------------
    blocking = [o for o in open_objs if o.blocking]
    if any(not o.resolvable for o in blocking):
        recommendation: Recommendation = "blocked"
        synthesis = "Unresolvable blocker (privacy/router) — human decision required."
    elif any(o.kind in ("insufficient_evidence", "thin_topic") for o in blocking):
        recommendation = "needs_more_evidence"
        synthesis = "No hard blocker, but ledger evidence is below the consensus bar."
    elif blocking:
        recommendation = "blocked"
        synthesis = "A contradiction leaked past quarantine — promotion must not proceed."
    else:
        recommendation = "approve_for_review"
        synthesis = (f"All objections resolved against real ledger state in "
                     f"{rounds_run} round(s); a manual promotion review packet can be prepared.")
    transcript.append(LoopStatement(rounds_run, "synthesis_chair", "synthesize", [synthesis]))
    transcript.append(LoopStatement(
        rounds_run, "promotion_judge", "dry_run_only",
        [f"recommendation={recommendation}; manual approval required before any real promotion"],
        blocks_promotion=recommendation != "approve_for_review"))

    return LoopResult(
        topic=topic,
        rounds_run=rounds_run,
        fixed_point=fixed_point,
        transcript=transcript,
        objections_open=[asdict(o) for o in open_objs],
        objections_resolved=resolved,
        synthesis=synthesis,
        promotion_recommendation=recommendation,
    )
