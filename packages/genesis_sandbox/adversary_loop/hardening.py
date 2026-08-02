# -*- coding: utf-8 -*-
"""Staged hardening router -- turn a confirmed breach into an operator-gated PROPOSAL, never a
hand-patch of a defense internal.

BINDING: this module does NOT edit ``injection_guard``, the moral core, the action lane, the
promotion gate, or any other defense. It writes a SIGNED-READY PROPOSAL MANIFEST to a staging dir
(auditable, reversible) describing the breach + a suggested mitigation CLASS + the (read-only)
target module. Applying it is a separate, explicit human step. Mirrors the candidate promotion
gate: default-deny, exact operator phrase, staging-only.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from packages.genesis_sandbox.adversary_loop.breach_ledger import BreachReceipt

REQUIRED_APPROVAL_PHRASE = "APPROVE STAGED DEFENSE HARDENING PROPOSAL"

_DEFAULT_STAGING = Path(__file__).resolve().parent / "_hardening_staging"

# Read-only reference to the defense module each surface lives in (for the operator to find it).
_SURFACE_MODULE = {
    "a": "packages/conformal_gate/live_wiring.py + packages/base_brain/zero_user_answer.py",
    "b": "packages/advisor_loop/advisor_session.py + packages/graph_scale/moral_invariants.py",
    "c": "packages/genesis_sandbox/moral_gate.py + packages/graph_scale/moral_invariants.py",
    "d": "packages/graph_scale/injection_guard.py",
    "e": "packages/os_action_lane/risk.py",
    "f": "packages/candidate_promotion_gate/gate.py",
}


def _suggest_mitigation(receipt: BreachReceipt) -> str:
    """Derive a mitigation CLASS from the finding's structure (not a code patch)."""
    tech = receipt.technique
    used = set(tech.split("+")) - {"", "seed"}
    s = receipt.surface
    if s == "c" and receipt.outcome == "GAP":
        # the moral text screen runs raw patterns -- it has NO de-obfuscation at all (unlike the
        # injection guard). The highest-leverage fix is to adopt the guard's normalizer.
        return ("The moral gate's text screen matches RAW text (no de-obfuscation). Route intent "
                "text through injection_guard._normalize_for_detection (confusable-fold + spaced-out "
                "collapse) BEFORE the moral/harm patterns run, so obfuscated harm-intent is caught by "
                "the heuristic ring too. The inviolable fingerprint core is untouched by this change.")
    if s == "d":
        if "filler_insert" in used:
            return ("Widen the frame-bound override/harm patterns to tolerate inserted filler tokens "
                    "between a trigger verb and its object (currently a fixed-adjacency regex).")
        if "synonym_swap" in used:
            return ("Expand the trigger lexicon (or move to a semantic/embedding screen) so a synonym "
                    "outside the fixed verb set is still caught.")
        if used & {"space_out", "confusable_fold"}:
            return ("A CLAIMED de-obfuscation class still slipped: the normalization restores the "
                    "text but the pattern misses it -- re-run the patterns on the normalized text AND "
                    "widen the frame.")
        if used & {"base64_wrap", "rot13_wrap"}:
            return ("Encoded-payload wrappers: detect the decode-and-execute intent (already partly "
                    "covered) and refuse to act on decoded content -- treat as data.")
        return ("Novel obfuscation class beyond the guard's precision boundary; add it to the "
                "de-obfuscation normalizer and keep defense-in-depth as the backstop.")
    if s == "e":
        return ("The risk classifier under-estimated a whole-disk/irreversible command shape. Add its "
                "form (e.g. long-form flags, alternate rm/dd/mkfs spellings) to the CATASTROPHIC set in "
                "os_action_lane/risk.py so the catastrophic confirm floor is never evaded.")
    if s == "a":
        if "whitebox" in tech:
            return ("The source-verified pass-through trusts in-result flags (fabricated_facts / "
                    "composition_vocabulary_closed). Re-derive provenance from the certificate's "
                    "evidence rather than trusting a self-attested flag on the result being gated.")
        return ("A must-abstain query was answered confidently. Tighten the precision/abstention gate "
                "(named-in-query + graded-confidence threshold) for this query shape.")
    if s == "b":
        return ("Tighten the moral screen's fabrication/obey patterns for distanced phrasing; the "
                "operator-signed promotion gate + No-LLM brain-content rule remain the real backstop "
                "before enshrinement.")
    if s == "c":
        return ("STRUCTURAL moral finding -- escalate to operator immediately; do not auto-modify the "
                "inviolable core.")
    if s == "f":
        return ("Promotion signature/phrase check was bypassed -- treat as critical; verify the exact "
                "phrase + operator_confirmed + production_store_mutated invariants.")
    return "Review the finding and design a targeted mitigation; keep defense-in-depth."


@dataclass
class StagedHardeningProposal:
    proposal_id: str
    surface: str
    surface_name: str
    signature: str
    severity: str | None
    outcome: str
    target_module: str
    repro_input: str
    repro_technique: str
    observed_behavior: dict[str, Any]
    suggested_mitigation: str
    backstop: str | None
    status: str = "staged_proposal"       # never 'applied' -- applying is a separate human step
    operator_ack: bool = False
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    manifest_path: str | None = None
    # hard invariants -- this router can NEVER do these:
    edits_defense_code: bool = False
    auto_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HardeningRouter:
    def __init__(self, staging_dir: str | Path | None = None) -> None:
        self.dir = Path(staging_dir) if staging_dir else _DEFAULT_STAGING
        self.dir.mkdir(parents=True, exist_ok=True)

    def propose(self, receipt: BreachReceipt) -> StagedHardeningProposal:
        pid = "harden_" + hashlib.sha256(
            (receipt.signature + receipt.ts).encode("utf-8")).hexdigest()[:16]
        proposal = StagedHardeningProposal(
            proposal_id=pid, surface=receipt.surface, surface_name=receipt.surface_name,
            signature=receipt.signature, severity=receipt.severity, outcome=receipt.outcome,
            target_module=_SURFACE_MODULE.get(receipt.surface, "unknown"),
            repro_input=receipt.attack_input, repro_technique=receipt.technique,
            observed_behavior=receipt.observed, suggested_mitigation=_suggest_mitigation(receipt),
            backstop=receipt.backstop,
        )
        path = self.dir / f"{pid}.json"
        path.write_text(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8")
        proposal.manifest_path = str(path)
        return proposal

    def propose_all(self, receipts: list[BreachReceipt], *, dedupe: bool = True) -> list[StagedHardeningProposal]:
        seen: set[str] = set()
        out: list[StagedHardeningProposal] = []
        for r in receipts:
            if dedupe and r.signature in seen:
                continue
            seen.add(r.signature)
            out.append(self.propose(r))
        return out

    def acknowledge(self, proposal: StagedHardeningProposal, *, operator_confirmed: bool,
                    confirmation_phrase: str) -> dict[str, Any]:
        """Default-deny operator acknowledgement. Even on a correct phrase this only MARKS the
        proposal acknowledged -- it NEVER applies a change (applying defense code is a separate,
        explicit human action)."""
        reasons: list[str] = []
        if not operator_confirmed:
            reasons.append("operator_confirmation_required")
        if (confirmation_phrase or "").strip() != REQUIRED_APPROVAL_PHRASE:
            reasons.append("required_phrase_mismatch")
        if reasons:
            return {"acknowledged": False, "applied": False, "reasons": reasons,
                    "proposal_id": proposal.proposal_id}
        proposal.operator_ack = True
        proposal.status = "operator_acknowledged_not_applied"
        if proposal.manifest_path:
            Path(proposal.manifest_path).write_text(
                json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8")
        return {"acknowledged": True, "applied": False,
                "note": "acknowledged for hardening; defense code is NOT modified by this router",
                "proposal_id": proposal.proposal_id}
