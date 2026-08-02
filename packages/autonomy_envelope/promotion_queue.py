# -*- coding: utf-8 -*-
"""Nightly operator-confirmed promotion queue; nothing here can authorize a merge.

The loop may inject into the CANDIDATE/STAGING graph autonomously (reversible, unshipped). A
write to the SHIPPED/production graph is different: it is NEVER autonomous. When the loop
nominates a candidate for shipping, the envelope QUEUES it here — a batch that waits for an
operator's morning review.

Default-deny (mirrors ``packages.candidate_promotion_gate`` and
``packages.local_memory_operator_confirmation``): only an exact confirmation phrase + a literal
``True`` operator-confirmed flag creates an unsigned staging receipt. Even then the
production/shipped store is NOT mutated — ``production_store_mutated`` stays False. The receipt
grants no merge authority; a strict detached signature and live-context match remain required at
the eventual side-effect boundary. Refused or staged batches remain pending.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.autonomy_envelope.audit_ledger import AuditLedger

# Typo-proof gate: the operator must type this EXACTLY to sign a nightly batch.
REQUIRED_CONFIRMATION_PHRASE = "SIGN NIGHTLY AUTONOMY PROMOTION BATCH"

# Invariants stamped on every manifest — the promises the artifact makes.
INVARIANTS = {
    "external_llm": False,
    "external_sllm": False,
    "shipped_graph_write": False,       # this artifact never itself writes the shipped graph
    "production_store_mutated": False,
    "auto_promote": False,              # never auto-applied
    "human_approval_required": True,
    "signed_manifest_required": True,
    "rollback_required": True,
    "proof_only": True,
    # This path records an interactive operator confirmation and stages a receipt.
    # It is not a detached cryptographic signature and grants no merge authority.
    "cryptographically_signed": False,
    "merge_authorized": False,
    "authorization_scope": "staging_only",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _batch_id(entries: tuple[dict[str, Any], ...], operator_id: str) -> str:
    """Bind the staging receipt ID to complete pending content, not item IDs alone."""
    digest = hashlib.sha256(
        (_canonical(entries) + "::" + operator_id).encode("utf-8")
    ).hexdigest()[:24]
    return f"nightly_promotion_confirmed_{digest}"


@dataclass
class NightlyPromotionQueue:
    """Pending shipped-graph promotions awaiting review and external authorization."""

    staging_dir: Path
    ledger: AuditLedger
    NAME: str = "nightly promotion queue"

    def _pending_path(self) -> Path:
        return Path(self.staging_dir) / "pending_batch.jsonl"

    # ── queue (the loop's side — autonomous, but only ever ENQUEUES, never applies) ──────
    def queue(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Enqueue a shipped-graph promotion for morning review. Never apply it.

        THE FOUR CHECKS RIDE ALONG, AND THEY CAN ONLY TIGHTEN. `packages.self_check` earned its
        authority on 2026-07-29 by refusing five confident-and-wrong results and still allowing two real
        ones, and then sat with zero consumers. What its own docstring says the operator's signature was
        actually doing is an INDEPENDENT MEASUREMENT, so that measurement now travels with the review
        packet: whatever evidence the entry carries is checked, the verdict is attached, and an entry
        whose preflight is red is marked so it cannot be batch-approved without the failure being seen.

        Authority is unchanged and deliberately so. `operator-signed, default-deny` is a standing
        constraint, so nothing here grants a promotion, shortens the path, or turns a refusal into an
        approval -- the status only ever becomes MORE restrictive, never less. An entry carrying no
        evidence keeps the plain pending status rather than being failed for it, because a queue is not
        the place to demand measurements that the producer may legitimately not have."""
        rec = {
            "item_id": str(entry.get("item_id", "")) or hashlib.sha256(
                _canonical(entry).encode("utf-8")).hexdigest()[:16],
            "title": str(entry.get("title", ""))[:200],
            "queued_at": _utc_now_iso(),
            "payload": entry,
            "production_store_mutated": False,
            "status": "pending_operator_signature",
        }
        pf = self._preflight_of(entry)
        if pf is not None:
            rec["preflight"] = pf
            if not pf["may_promote"]:
                rec["status"] = "pending_operator_signature_preflight_failed"
        p = self._pending_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(rec) + "\n")
        self.ledger.append("promotion_queued", {"item_id": rec["item_id"], "title": rec["title"]})
        return rec

    _PREFLIGHT_FIELDS = ("observed_source", "intended_source", "visible_frac", "base_rate", "n",
                         "target_size", "unit_size", "same", "different", "real_score",
                         "control_score", "overlap")

    def _preflight_of(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """The four checks on whatever evidence the entry carries. None when it carries none.

        Import is local and failure is swallowed on purpose: a promotion QUEUE must not become
        unavailable because a measurement organ raised. Losing the extra check degrades the packet;
        losing the queue would lose the operator's only path to review anything."""
        ev = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else entry
        kw = {k: ev[k] for k in self._PREFLIGHT_FIELDS if isinstance(ev, dict) and k in ev}
        if not kw:
            return None
        try:
            from packages.self_check import preflight
            return preflight.run(str(entry.get("title", "") or entry.get("item_id", ""))[:200],
                                 **kw).as_dict()
        except Exception as exc:                                    # noqa: BLE001
            return {"may_promote": False, "claim": "preflight unavailable",
                    "blocked_by": [f"preflight raised: {exc}"], "checks": []}

    def pending(self) -> list[dict[str, Any]]:
        p = self._pending_path()
        if not p.exists():
            return []
        out: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def pending_count(self) -> int:
        return len(self.pending())

    # ── sign (the operator's side — morning batch approval) ──────────────────────────────
    def sign_batch(
        self,
        *,
        operator_confirmed: bool,
        confirmation_phrase: str,
        operator_id: str = "operator",
        item_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage exactly one selected promotion item after explicit confirmation.

        A receipt containing multiple candidates cannot be consumed by the shipped
        graph landing boundary and obscures which candidate the operator reviewed.
        Therefore an ambiguous queue fails closed; ``item_id`` is mandatory whenever
        more than one valid pending item exists. Production is never mutated here.
        """
        all_pending = self.pending()
        reasons: list[str] = []
        if operator_confirmed is not True:
            reasons.append("operator_confirmation_required")
        if (
            not isinstance(confirmation_phrase, str)
            or confirmation_phrase.strip() != REQUIRED_CONFIRMATION_PHRASE
        ):
            reasons.append("required_phrase_mismatch")
        if not isinstance(operator_id, str) or not operator_id.strip():
            reasons.append("operator_id_invalid")
        if not all_pending:
            reasons.append("no_pending_promotions")

        if reasons:
            self.ledger.append("batch_sign_refused", {"reasons": reasons,
                                                       "pending": len(all_pending)})
            return {
                **INVARIANTS,
                "allowed": False,
                "signed": False,
                "reasons": reasons,
                "pending": len(all_pending),
                "manifest_path": None,
            }

        if any(not isinstance(entry, dict) for entry in all_pending):
            item_ids: tuple[str, ...] = ()
        else:
            item_ids = tuple(
                str(entry.get("item_id", "")).strip()
                for entry in all_pending
            )
        if (
            len(item_ids) != len(all_pending)
            or any(not item_id for item_id in item_ids)
        ):
            self.ledger.append(
                "batch_confirmation_refused",
                {
                    "reason": "pending_batch_invalid",
                    "pending": len(all_pending),
                },
            )
            return {
                **INVARIANTS,
                "allowed": False,
                "staging_allowed": False,
                "signed": False,
                "reasons": ["pending_batch_invalid"],
                "pending": len(all_pending),
                "manifest_path": None,
            }

        selected_item_id = item_id.strip() if isinstance(item_id, str) else ""
        if not selected_item_id and len(all_pending) != 1:
            self.ledger.append(
                "batch_confirmation_refused",
                {
                    "reason": "single_promotion_selection_required",
                    "pending": len(all_pending),
                },
            )
            return {
                **INVARIANTS,
                "allowed": False,
                "staging_allowed": False,
                "signed": False,
                "reasons": ["single_promotion_selection_required"],
                "pending": len(all_pending),
                "manifest_path": None,
            }
        if selected_item_id:
            selected = [
                entry
                for entry in all_pending
                if entry.get("item_id") == selected_item_id
            ]
            if len(selected) != 1:
                self.ledger.append(
                    "batch_confirmation_refused",
                    {
                        "reason": "promotion_item_not_found_or_ambiguous",
                        "item_id": selected_item_id,
                    },
                )
                return {
                    **INVARIANTS,
                    "allowed": False,
                    "staging_allowed": False,
                    "signed": False,
                    "reasons": [
                        "promotion_item_not_found_or_ambiguous"
                    ],
                    "pending": len(all_pending),
                    "manifest_path": None,
                }
            pending = selected
        else:
            pending = [all_pending[0]]
        item_ids = (str(pending[0]["item_id"]),)
        selected_payload = pending[0].get("payload")
        if (
            isinstance(selected_payload, dict)
            and selected_payload.get("promotion_kind")
            == "graph_store_candidate"
        ):
            manifest_sha256 = selected_payload.get(
                "mutation_batch_manifest_sha256"
            )
            if (
                not isinstance(manifest_sha256, str)
                or len(manifest_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in manifest_sha256
                )
            ):
                self.ledger.append(
                    "batch_confirmation_refused",
                    {
                        "reason": (
                            "mutation_batch_manifest_digest_invalid"
                        ),
                        "item_id": item_ids[0],
                    },
                )
                return {
                    **INVARIANTS,
                    "allowed": False,
                    "staging_allowed": False,
                    "signed": False,
                    "reasons": [
                        "mutation_batch_manifest_digest_invalid"
                    ],
                    "pending": len(all_pending),
                    "manifest_path": None,
                }

        normalized_operator_id = operator_id.strip()
        batch_id = _batch_id(tuple(pending), normalized_operator_id)
        path = Path(self.staging_dir) / f"{batch_id}.json"
        if path.exists():
            self.ledger.append(
                "batch_confirmation_refused",
                {"reason": "staging_receipt_collision", "batch_id": batch_id},
            )
            return {
                **INVARIANTS,
                "allowed": False,
                "staging_allowed": False,
                "signed": False,
                "reasons": ["staging_receipt_collision"],
                "pending": len(pending),
                "manifest_path": None,
            }
        manifest = {
            **INVARIANTS,
            "batch_id": batch_id,
            "confirmed_at": _utc_now_iso(),
            "operator_id": normalized_operator_id,
            "operator_confirmed": True,
            "signed": False,
            "staging_allowed": True,
            "status": "operator_confirmed_staged",
            "attestation_level": "interactive_confirmation",
            "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
            "item_ids": list(item_ids),
            "item_count": len(item_ids),
            "entries": pending,
            "note": (
                "Operator-confirmed nightly promotion batch staged for external review. This "
                "receipt is not a cryptographic signature and cannot authorize a shipped-graph "
                "merge. The production store remains untouched."
            ),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        try:
            with path.open("xb") as handle:
                handle.write(receipt_bytes)
        except FileExistsError:
            # A concurrent writer or pre-existing path is never parsed or trusted.
            self.ledger.append(
                "batch_confirmation_refused",
                {"reason": "staging_receipt_collision", "batch_id": batch_id},
            )
            return {
                **INVARIANTS,
                "allowed": False,
                "staging_allowed": False,
                "signed": False,
                "reasons": ["staging_receipt_collision"],
                "pending": len(pending),
                "manifest_path": None,
            }
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        # Pending remains pending until a separately verified cryptographic authorization
        # and merge boundary exists. A phrase receipt must never consume merge work.
        self.ledger.append(
            "batch_confirmed_staged",
            {
                "batch_id": manifest["batch_id"],
                "item_count": manifest["item_count"],
                "operator_id": normalized_operator_id,
                "staging_receipt_sha256": receipt_sha256,
            },
        )
        return {
            **manifest,
            "allowed": True,
            "signed": False,
            "manifest_path": str(path),
            "staging_receipt_sha256": receipt_sha256,
        }

    def status(self) -> dict[str, Any]:
        return {
            "name": self.NAME,
            "pending": self.pending_count(),
            "required_confirmation_phrase": REQUIRED_CONFIRMATION_PHRASE,
            "staging_dir": str(self.staging_dir),
            **INVARIANTS,
        }


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
