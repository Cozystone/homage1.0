"""Candidate Promotion Gate (v0).

Turns a human-reviewed candidate (from the agentic review queue) into an
auditable, operator-signed *promotion request* — and nothing more. It exists to
ENFORCE the ATANOR rule: no candidate is promoted without explicit human
approval, and even with approval the production store is never silently mutated.

Design mirrors `construction_bank.promotion_gate` and
`local_memory_operator_confirmation.gate`:

- Default-deny. Eligibility requires the operator to have already *approved* the
  item in the review queue, plus provenance + confidence + non-critical risk.
- Operator confirmation requires an exact phrase (typo-proof gate).
- A confirmed promotion writes only a SIGNED MANIFEST artifact to a staging dir
  (auditable, reversible). It does NOT write the production cloud brain — that
  remains a separate, later gate. `production_store_mutated` stays False.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_CONFIRMATION_PHRASE = "PROMOTE REVIEWED CANDIDATES TO VERIFIED STAGING"

# Only these review-item types are ever promotable in v0. Raw trajectories and
# unscored sources are not.
PROMOTABLE_ITEM_TYPES = {"cloud_candidate", "construction_candidate"}

FORBIDDEN_TERMS = (
    "local_brain_direct_write",
    "local brain write",
    "production write",
    "production_store_mutated",
    "candidate promotion",
    "auto promote",
    "auto-promotion",
    "auto commit",
    "auto push",
    "raw_private_memory",
    "api_key",
    "api key",
    "secret",
    "token",
    "password",
)

# Minimal hard floor used in unattended intent-staging mode. Incidental security
# vocabulary on a public page ("personal access token", "secret scanning") is NOT
# a reason to block; only genuine private-memory / mutation-directive signals are.
AUTO_HARD_FLOOR_TERMS = (
    "raw_private_memory",
    "local_brain_direct_write",
    "production_store_mutated",
    "local brain write",
    "production write",
)

INVARIANTS = {
    "external_llm": False,
    "external_sllm": False,
    "local_brain_write": False,
    "production_store_mutated": False,
    "production_activation": False,
    "auto_promote": False,
    "auto_commit": False,
    "auto_push": False,
    "signed_manifest_required": True,
    "rollback_required": True,
    "human_approval_required": True,
    "proof_only": True,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PromotionThresholds:
    min_confidence: float = 0.5
    allowed_risk_levels: tuple[str, ...] = ("low", "medium")
    require_source_refs: bool = True
    require_status_approved: bool = True
    max_batch: int = 50


@dataclass(frozen=True)
class PromotionEntry:
    item_id: str
    item_type: str
    title: str
    risk_level: str
    confidence: float
    source_ref_count: int
    eligible: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateIntentPlan:
    """Immutable, byte-exact plan for one unattended intent artifact.

    Planning is pure: no directory or file is created.  A caller can therefore
    reserve the exact payload byte count before applying the plan.
    """

    manifest: dict[str, Any]
    manifest_bytes: bytes
    manifest_path: Path
    newly_staged_ids: tuple[str, ...]


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
            " ".join(str(ref) for ref in (item.get("source_refs") or [])),
            str(item.get("risk_level", "")),
        ]
    ).lower()


def _contains_forbidden(item: dict[str, Any]) -> bool:
    return any(term in _item_text(item) for term in FORBIDDEN_TERMS)


def _contains_hard_floor(item: dict[str, Any]) -> bool:
    return any(term in _item_text(item) for term in AUTO_HARD_FLOOR_TERMS)


def evaluate_candidate_item(
    item: dict[str, Any],
    thresholds: PromotionThresholds = PromotionThresholds(),
    *,
    auto_mode: bool = False,
) -> PromotionEntry:
    """Pure eligibility check for a single review-queue item dict.

    Default-deny in operator mode. In ``auto_mode`` the result can only be used
    to stage a non-authoritative intent. The human-approval and risk-level gates
    are omitted for that proposal census; provenance, confidence, and a minimal
    private/mutation hard floor remain mandatory.
    """

    reasons: list[str] = []
    item_type = str(item.get("item_type", ""))
    risk_level = str(item.get("risk_level", "high"))
    status = str(item.get("status", "pending"))
    try:
        confidence = float(item.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    source_refs = item.get("source_refs") or []
    source_ref_count = len(source_refs) if isinstance(source_refs, list) else 0

    if item_type not in PROMOTABLE_ITEM_TYPES:
        reasons.append(f"item_type_not_promotable:{item_type or 'unknown'}")
    if not auto_mode and thresholds.require_status_approved and status != "approved":
        reasons.append(f"not_human_approved:{status}")
    if not auto_mode and risk_level not in thresholds.allowed_risk_levels:
        reasons.append(f"risk_level_blocked:{risk_level}")
    if thresholds.require_source_refs and source_ref_count == 0:
        reasons.append("missing_source_refs")
    if confidence < thresholds.min_confidence:
        reasons.append("confidence_below_threshold")
    if auto_mode:
        if _contains_hard_floor(item):
            reasons.append("private_or_mutation_hard_floor")
    elif _contains_forbidden(item):
        reasons.append("forbidden_or_private_signal")

    return PromotionEntry(
        item_id=str(item.get("item_id", "")),
        item_type=item_type,
        title=str(item.get("title", ""))[:160],
        risk_level=risk_level,
        confidence=round(confidence, 4),
        source_ref_count=source_ref_count,
        eligible=not reasons,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


class CandidatePromotionGate:
    def __init__(self, *, staging_dir: Path | str | None = None, thresholds: PromotionThresholds = PromotionThresholds()) -> None:
        self.thresholds = thresholds
        self.staging_dir = Path(staging_dir) if staging_dir else Path("runtime/agentic_micro_os/promotions")

    # ----- evaluation / drafting -------------------------------------------------

    def evaluate(self, items: list[dict[str, Any]], item_ids: list[str] | None = None) -> list[PromotionEntry]:
        wanted = set(item_ids) if item_ids else None
        entries: list[PromotionEntry] = []
        for item in items:
            if wanted is not None and str(item.get("item_id", "")) not in wanted:
                continue
            entries.append(evaluate_candidate_item(item, self.thresholds))
        # Recorded HERE and not inside `evaluate_candidate_item`, whose purity is worth keeping:
        # it is the composable check, this is the organ boundary where a decision is actually made.
        # Reflex tier (plan v5 §2) -- un-overridable, so obliged to be observable, and the gate was
        # persisting only what it ALLOWED. For a default-deny gate the refusals are the substance.
        from packages.candidate_promotion_gate.refusal_ledger import record_verdicts
        record_verdicts(entries, mode="operator")
        return entries

    def draft_manifest(self, items: list[dict[str, Any]], item_ids: list[str] | None = None, created_by: str = "operator") -> dict[str, Any]:
        entries = self.evaluate(items, item_ids)
        eligible = [entry for entry in entries if entry.eligible]
        eligible_ids = tuple(entry.item_id for entry in eligible)
        manifest_id = _manifest_id(eligible_ids, created_by, draft=True)
        return {
            **INVARIANTS,
            "manifest_id": manifest_id,
            "created_at": _utc_now(),
            "created_by": created_by,
            "status": "review_ready" if eligible_ids else "draft",
            "operator_confirmed": False,
            "promotion_approved_staged": False,
            "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
            "eligible_ids": list(eligible_ids),
            "eligible_count": len(eligible_ids),
            "evaluated_count": len(entries),
            "thresholds": asdict(self.thresholds),
            "entries": [entry.to_dict() for entry in entries],
        }

    # ----- confirmation / signing ------------------------------------------------

    def confirm_promotion(
        self,
        items: list[dict[str, Any]],
        *,
        item_ids: list[str] | None,
        operator_confirmed: bool,
        confirmation_phrase: str,
        operator_id: str = "operator",
        truth_maintenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Default-deny. Only an exact phrase + confirmed flag + eligible items
        produces a signed, staged promotion manifest. Never writes production.

        ``truth_maintenance`` (optional, additive) is a per-item provenance bundle
        (JTMS justification + ATMS environment + epistemic tier) supplied by the
        contamination firewall. When given, it is PERSISTED alongside the signed manifest
        for audit/retraction; the promotion DECISION (operator phrase + default-deny) is
        entirely unaffected. Default None -> the written manifest is byte-identical to
        before (no new key)."""

        draft = self.draft_manifest(items, item_ids, created_by=operator_id)
        reasons: list[str] = []
        if not operator_confirmed:
            reasons.append("operator_confirmation_required")
        if (confirmation_phrase or "").strip() != REQUIRED_CONFIRMATION_PHRASE:
            reasons.append("required_phrase_mismatch")
        if not draft["eligible_ids"]:
            reasons.append("no_eligible_candidates")

        if reasons:
            return {
                **draft,
                "allowed": False,
                "promotion_approved_staged": False,
                "reasons": reasons,
                "manifest_path": None,
            }

        signed = {
            **draft,
            "manifest_id": _manifest_id(tuple(draft["eligible_ids"]), operator_id, draft=False),
            "status": "operator_approved_staged",
            "operator_confirmed": True,
            "operator_id": operator_id,
            "promotion_approved_staged": True,
            "signed_at": _utc_now(),
            "production_store_mutated": False,
            "production_activation": False,
            "note": (
                "Operator-signed promotion of reviewed candidates to verified STAGING. "
                "The production cloud brain is NOT mutated by this step; a separate "
                "production-merge gate remains required."
            ),
            "reasons": ["operator_confirmed_staged_promotion"],
        }
        # additive persistence: only add the key when the firewall supplied provenance,
        # so a plain confirm_promotion() writes a byte-identical manifest.
        if truth_maintenance is not None:
            signed["truth_maintenance"] = truth_maintenance
        path = self._write_manifest(signed)
        signed["manifest_path"] = str(path)
        signed["allowed"] = True
        return signed

    def stage_candidate_intents(
        self,
        items: list[dict[str, Any]],
        *,
        already_staged: set[str] | None = None,
    ) -> dict[str, Any]:
        """Stage non-authoritative candidate intents for operator review.

        This is the maximum authority available to an unattended loop. The
        durable artifact records eligible candidate ids, but it is not a
        promotion approval, activation, or production write. Mutation telemetry
        is explicit because writing the intent artifact is still a staging
        mutation even though the shipped store remains untouched.
        """

        plan = self.plan_candidate_intents(
            items,
            already_staged=already_staged,
        )
        if plan is None:
            return self._no_new_candidate_intent()
        return self.apply_candidate_intent_plan(plan)

    def plan_candidate_intents(
        self,
        items: list[dict[str, Any]],
        *,
        already_staged: set[str] | None = None,
        created_at: str | None = None,
    ) -> CandidateIntentPlan | None:
        """Return the exact candidate-intent bytes, staging nothing.

        Writes no manifest and mutates no staging state, so the returned bytes stay byte-determined
        by the inputs. It does append a verdict receipt: the receipt is not the artifact and cannot
        reach the bytes, and this is the UNATTENDED path -- the one that runs with nobody watching,
        and the one where a run that refused everything used to return ``None`` leaving no trace at
        all. That silence is the case the receipt exists for.
        """

        already = already_staged or set()
        entries = [
            evaluate_candidate_item(
                item,
                self.thresholds,
                auto_mode=True,
            )
            for item in items
        ]
        from packages.candidate_promotion_gate.refusal_ledger import record_verdicts
        record_verdicts(entries, mode="auto")
        eligible = tuple(
            entry.item_id
            for entry in entries
            if entry.eligible
            and entry.item_id
            and entry.item_id not in already
        )
        if not eligible:
            return None
        intent = {
            **INVARIANTS,
            "manifest_id": _intent_id(eligible),
            "created_at": created_at or _utc_now(),
            "created_by": "autonomous_loop",
            "status": "candidate_intent_staged",
            "operator_confirmed": False,
            "auto_promoted": False,
            "candidate_promotion": False,
            "candidate_intent_only": True,
            "promotion_approved_staged": False,
            "production_store_mutated": False,
            "production_activation": False,
            "production_merge_attempted": False,
            "newly_promoted_ids": [],
            "newly_staged_ids": list(eligible),
            "eligible_ids": list(eligible),
            "note": (
                "The unattended loop staged a non-authoritative candidate intent. "
                "No promotion was approved, and no production merge or activation "
                "was attempted. Operator review remains required."
            ),
        }
        payload = self._manifest_bytes(intent)
        path = self.staging_dir / f"{intent['manifest_id']}.json"
        return CandidateIntentPlan(
            manifest=intent,
            manifest_bytes=payload,
            manifest_path=path,
            newly_staged_ids=eligible,
        )

    def apply_candidate_intent_plan(
        self,
        plan: CandidateIntentPlan,
    ) -> dict[str, Any]:
        """Apply one previously planned intent using its exact planned bytes."""

        if type(plan) is not CandidateIntentPlan:
            raise TypeError("CandidateIntentPlan is required")
        expected_bytes = self._manifest_bytes(plan.manifest)
        expected_path = (
            self.staging_dir / f"{plan.manifest.get('manifest_id', '')}.json"
        )
        if (
            plan.manifest_bytes != expected_bytes
            or plan.manifest_path != expected_path
            or tuple(plan.manifest.get("newly_staged_ids") or ())
            != plan.newly_staged_ids
            or plan.manifest.get("status") != "candidate_intent_staged"
            or plan.manifest.get("candidate_intent_only") is not True
            or plan.manifest.get("operator_confirmed") is not False
            or plan.manifest.get("promotion_approved_staged") is not False
            or plan.manifest.get("production_store_mutated") is not False
            or plan.manifest.get("production_activation") is not False
            or plan.manifest.get("production_merge_attempted") is not False
        ):
            raise ValueError("candidate intent plan integrity mismatch")
        path = self._write_manifest_bytes(
            plan.manifest_path,
            plan.manifest_bytes,
        )
        return {
            **plan.manifest,
            "allowed": True,
            "auto_promoted": 0,
            "candidate_intents_staged": len(plan.newly_staged_ids),
            "candidate_staging_mutated": True,
            "mutation_performed": True,
            "manifest_path": str(path),
            "manifest_write_bytes": len(plan.manifest_bytes),
        }

    def auto_promote(
        self,
        items: list[dict[str, Any]],
        *,
        already_promoted: set[str] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper; unattended callers can only stage intents."""

        return self.stage_candidate_intents(
            items,
            already_staged=already_promoted,
        )

    def list_manifests(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.staging_dir.exists():
            return []
        files = sorted(self.staging_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        manifests: list[dict[str, Any]] = []
        for file in files[:limit]:
            try:
                manifests.append(json.loads(file.read_text(encoding="utf-8")))
            except Exception:  # pragma: no cover - skip corrupt artifact
                continue
        return manifests

    def status(self, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        manifests = self.list_manifests()
        signed_manifests = [
            manifest
            for manifest in manifests
            if manifest.get("operator_confirmed") is True
            and manifest.get("promotion_approved_staged") is True
        ]
        intent_manifests = [
            manifest
            for manifest in manifests
            if manifest.get("status") == "candidate_intent_staged"
            and manifest.get("candidate_intent_only") is True
        ]
        eligible_now = 0
        if items is not None:
            eligible_now = sum(1 for entry in self.evaluate(items) if entry.eligible)
        return {
            **INVARIANTS,
            "gate_available": True,
            "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
            "thresholds": asdict(self.thresholds),
            "eligible_now": eligible_now,
            "signed_manifests": len(signed_manifests),
            "candidate_intent_manifests": len(intent_manifests),
            "staging_artifacts": len(manifests),
            "candidate_staging_artifacts_present": bool(intent_manifests),
            "recent_manifests": manifests[:5],
            "staging_dir": str(self.staging_dir),
        }

    def _write_manifest(self, manifest: dict[str, Any]) -> Path:
        path = self.staging_dir / f"{manifest['manifest_id']}.json"
        return self._write_manifest_bytes(
            path,
            self._manifest_bytes(manifest),
        )

    @staticmethod
    def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
        return json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

    def _write_manifest_bytes(self, path: Path, payload: bytes) -> Path:
        if path.parent != self.staging_dir:
            raise ValueError("candidate intent path escaped staging directory")
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    @staticmethod
    def _no_new_candidate_intent() -> dict[str, Any]:
        return {
            **INVARIANTS,
            "allowed": False,
            "auto_promoted": 0,
            "candidate_intents_staged": 0,
            "candidate_staging_mutated": False,
            "mutation_performed": False,
            "production_merge_attempted": False,
            "reason": "no_new_eligible",
            "newly_promoted_ids": [],
            "newly_staged_ids": [],
            "manifest_path": None,
            "manifest_write_bytes": 0,
        }


def _manifest_id(eligible_ids: tuple[str, ...], created_by: str, *, draft: bool) -> str:
    digest = hashlib.sha256(("|".join(sorted(eligible_ids)) + created_by).encode("utf-8")).hexdigest()[:16]
    prefix = "promotion_draft" if draft else "promotion_signed"
    return f"{prefix}_{digest}"


def _intent_id(eligible_ids: tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        ("|".join(sorted(eligible_ids)) + "autonomous_intent").encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"candidate_intent_{digest}"
