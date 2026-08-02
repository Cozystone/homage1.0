# -*- coding: utf-8 -*-
"""The operator-approval QUEUE — the daemon PROPOSES, the operator DISPOSES.

Every consensus-verified fact the acquisition loop produces overnight lands here as a promotable
CANDIDATE (``status="pending"``), never in the shipped graph. The only path from queue to a
persistent store runs through the EXISTING operator-signed gate
(``candidate_promotion_gate.CandidatePromotionGate.confirm_promotion``): default-deny, an exact
confirmation phrase, and it signs a manifest without ever mutating production. This module adds the
APPLY step the gate deliberately leaves separate — and guards it so injection is IMPOSSIBLE without
a valid operator signature.

Safety invariant (the whole point):
  * ``add_result`` only accepts a CONSENSUS-verified acquisition result (>= 2 domains + provenance).
  * items enter as ``pending`` — the gate rejects pending items, so an unattended run can never
    self-approve.
  * ``approve_and_apply`` writes facts to a store ONLY after ``confirm_promotion`` returns
    ``allowed and operator_confirmed`` (exact phrase + flag). No signature -> zero writes.
  * it refuses to target the shipped store handed to the daemon (a misconfiguration guard).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from packages.candidate_promotion_gate import (
    REQUIRED_CONFIRMATION_PHRASE,
    CandidatePromotionGate,
)
from packages.knowledge_acquisition.inject import inject_fact

# statuses an item moves through: pending (proposed) -> approved (operator review) -> applied (written)
VERIFIED_STATUSES = frozenset({"acquired", "injected"})


def _item_id(subject: str, predicate: str, obj: str) -> str:
    digest = hashlib.sha256(f"{subject.lower()}|{predicate.lower()}|{obj.lower()}".encode("utf-8"))
    return f"cloud_candidate_{digest.hexdigest()[:16]}"


def result_to_item(result: Any) -> dict[str, Any] | None:
    """Turn a CONSENSUS-verified ``AcquisitionResult`` into a promotable review-queue item
    (``status="pending"``). Returns None if the result is not a verified fact (no consensus /
    excluded / abstained) — such a result NEVER becomes a candidate (fabrication-0 at the queue)."""
    status = getattr(result, "status", "")
    domains = list(getattr(result, "domains", None) or [])
    urls = list(getattr(result, "urls", None) or [])
    subject = str(getattr(result, "entity", "") or "").strip()
    predicate = str(getattr(result, "predicate", "") or "").strip()
    obj = str(getattr(result, "object", "") or "").strip()
    rel_norm = str(getattr(result, "rel_norm", "") or "").strip()

    if status not in VERIFIED_STATUSES or len(domains) < 2 or not (subject and predicate and obj):
        return None

    n = len(domains)
    confidence = round(min(0.95, 0.6 + 0.1 * (n - 2)), 4)   # >= 2 domains -> >= 0.6 (clears 0.5 floor)
    return {
        "item_id": _item_id(subject, predicate, obj),
        "item_type": "cloud_candidate",
        "title": f"{subject} {rel_norm or predicate} = {obj}",
        "summary": (f"Web-mined relational fact reaching cross-domain consensus: "
                    f"{subject} {predicate} {obj}. Corroborated by {n} distinct domains "
                    f"({', '.join(domains)})."),
        "source_refs": urls,                    # provenance — the consensus evidence urls
        "risk_level": "low",
        "confidence": confidence,
        "status": "pending",                    # NOT approved — an unattended run cannot self-promote
        # payload the apply step needs (kept out of the gate's text scan):
        "fact": {"subject": subject, "predicate": predicate, "object": obj},
        "domains": domains,
        "urls": urls,
        "consensus_domains": n,
    }


class AcquisitionQueue:
    """A scoped JSON queue of candidate facts. ``path`` is ephemeral in the sealed gate."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, items: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")

    def add_result(self, result: Any) -> str | None:
        """Enqueue a verified acquisition result. Idempotent (dedup by fact id). Returns the item_id
        if enqueued (new), else None (rejected non-verified, or already queued)."""
        item = result_to_item(result)
        if item is None:
            return None
        items = self._load()
        if item["item_id"] in items:
            return None                          # already proposed — no duplicate
        items[item["item_id"]] = item
        self._save(items)
        return item["item_id"]

    def items(self) -> list[dict[str, Any]]:
        return list(self._load().values())

    def pending(self) -> list[dict[str, Any]]:
        return [it for it in self._load().values() if it.get("status") == "pending"]

    def by_status(self, status: str) -> list[dict[str, Any]]:
        return [it for it in self._load().values() if it.get("status") == status]

    # ---- the operator gate + apply (safety-critical) ------------------------------------------
    def approve_and_apply(self, target_root: Path | str, *, operator_confirmed: bool,
                          confirmation_phrase: str, staging_dir: Path | str,
                          operator_id: str = "operator", item_ids: list[str] | None = None,
                          forbid_root: Path | str | None = None,
                          firewall: Any = None, firewall_source_id: str | None = None) -> dict[str, Any]:
        """Operator-signed promotion + APPLY. Flips the requested pending items to ``approved`` (the
        operator's per-item review), runs them through ``confirm_promotion`` (default-deny + exact
        phrase), and ONLY on a valid signature injects each eligible fact into ``target_root`` with
        its web-consensus provenance. Without the signature: writes nothing.

        ``target_root`` must be an operator-designated store (an ephemeral / scoped store), never the
        shipped store the daemon reads — ``forbid_root`` (the shipped root) is refused outright.

        ``firewall`` (optional, additive, default None): a
        ``truth_maintenance.ContaminationFirewall``. When given, each APPLIED fact is rooted in the
        firewall's JTMS (via ``live_membrane.register_applied_fact``) so a later
        ``firewall.invalidate_source(src)`` flips it — and its dependents — OUT
        (dependency-directed retraction). ``firewall_source_id`` sets a SHARED source handle for the
        whole batch (invalidating it retracts every applied fact, i.e. "this source was revoked");
        omit it for a PER-ITEM handle (each fact individually retractable). Default None -> this
        method behaves byte-identically to before (no firewall calls, no extra return key)."""
        target_root = Path(target_root)
        if forbid_root is not None and target_root.resolve() == Path(forbid_root).resolve():
            return {"applied": 0, "allowed": False, "reasons": ["refused_target_is_shipped_store"],
                    "note": "apply target must be a scoped store, never the shipped graph"}

        items = self._load()
        wanted = set(item_ids) if item_ids else {i for i, it in items.items()
                                                 if it.get("status") == "pending"}
        # the operator's per-item approval: present a COPY marked approved to the gate (persisted
        # only if the signature succeeds, so a denied attempt leaves the queue pending/untouched).
        review = []
        for iid in wanted:
            it = items.get(iid)
            if not it:
                continue
            review.append({**it, "status": "approved"})

        gate = CandidatePromotionGate(staging_dir=staging_dir)
        signed = gate.confirm_promotion(review, item_ids=list(wanted),
                                        operator_confirmed=operator_confirmed,
                                        confirmation_phrase=confirmation_phrase,
                                        operator_id=operator_id)

        # HARD GATE: no signature -> no write. This is the airtight enforcement.
        if not (signed.get("allowed") is True and signed.get("operator_confirmed") is True
                and signed.get("promotion_approved_staged") is True):
            return {"applied": 0, "allowed": False,
                    "reasons": signed.get("reasons", []),
                    "manifest_path": signed.get("manifest_path"),
                    "signed": signed}

        eligible = set(signed.get("eligible_ids") or [])
        injected: list[dict[str, Any]] = []
        # optional retraction hook (default-off): root each APPLIED fact in the firewall's JTMS so
        # a later invalidate_source flips it OUT. Lazy import keeps promotion_queue's import surface
        # unchanged when no firewall is passed.
        _register = None
        firewall_sources: dict[str, str] = {}
        if firewall is not None:
            from packages.truth_maintenance.live_membrane import register_applied_fact as _register
        for iid in sorted(eligible):
            it = items.get(iid)
            if not it:
                continue
            fact = it.get("fact") or {}
            audit = inject_fact(target_root, fact.get("subject", ""), fact.get("predicate", ""),
                                fact.get("object", ""), it.get("domains") or [],
                                it.get("urls") or [])
            it["status"] = "applied"
            it["applied_manifest"] = signed.get("manifest_id")
            items[iid] = it
            injected.append({"item_id": iid, "fact": fact, "inject": audit})
            if _register is not None and audit.get("injected"):
                src = firewall_source_id or f"applied:{signed.get('manifest_id')}:{iid}"
                _register(firewall, fact.get("subject", ""), fact.get("predicate", ""),
                          fact.get("object", ""),
                          provenance=str(it.get("provenance") or "web-consensus"),
                          source_id=src,
                          consensus_domains=int(it.get("consensus_domains")
                                                or len(it.get("domains") or [])))
                firewall_sources[iid] = src
        self._save(items)
        result = {"applied": len(injected), "allowed": True,
                  "manifest_id": signed.get("manifest_id"),
                  "manifest_path": signed.get("manifest_path"),
                  "eligible_ids": sorted(eligible), "injected": injected,
                  "production_store_mutated": False}   # target is a scoped store, never production
        if firewall is not None:
            result["firewall_sources"] = firewall_sources   # retraction handles for applied facts
        return result
