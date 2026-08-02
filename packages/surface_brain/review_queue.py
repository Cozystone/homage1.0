from __future__ import annotations

import hashlib
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .audit_log import append_repair_audit_event
from .models import utc_now_iso
from .repair_rules import RepairRule, RepairSeverity, rule_from_dict
from .rule_registry import upsert_production_rule
from .storage import SURFACE_ROOT, ensure_dirs, read_json, write_json


CandidateStatus = Literal["pending", "approved", "rejected", "archived", "needs_edit"]


@dataclass(slots=True)
class RepairCandidate:
    candidate_id: str
    created_at: str
    source: str
    source_run_id: str | None
    feedback_id: str | None
    proposed_rule: dict[str, Any]
    status: CandidateStatus
    severity: RepairSeverity
    reason: str
    example_before: str | None = None
    example_after: str | None = None
    expected_effect: dict[str, Any] = field(default_factory=dict)
    risk_notes: list[str] = field(default_factory=list)
    review: dict[str, Any] = field(default_factory=lambda: {
        "reviewed_at": None,
        "reviewer": None,
        "decision": None,
        "comment": None,
    })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_path(candidate_id: str) -> Path:
    return SURFACE_ROOT / "review_queue" / f"{candidate_id}.json"


def _status_copy_dir(status: str) -> Path | None:
    if status == "rejected":
        return SURFACE_ROOT / "rejected_rules"
    if status == "archived":
        return SURFACE_ROOT / "archived_rules"
    return None


def _candidate_id(rule: RepairRule, source_run_id: str | None, index: int) -> str:
    digest = hashlib.sha256(f"{source_run_id}:{index}:{rule.rule_id}:{utc_now_iso()}".encode("utf-8")).hexdigest()[:16]
    return f"repair_candidate_{digest}"


def _candidate_from_rule(rule: RepairRule, source_run_id: str | None, index: int) -> RepairCandidate:
    high_safety = rule.severity == "high" and rule.action in {"move_to_trace", "replace", "remove"}
    return RepairCandidate(
        candidate_id=_candidate_id(rule, source_run_id, index),
        created_at=utc_now_iso(),
        source=rule.source,
        source_run_id=source_run_id,
        feedback_id=rule.created_from_feedback_id,
        proposed_rule=rule.to_dict(),
        status="pending",
        severity=rule.severity,
        reason=rule.description,
        expected_effect={
            "trace_hygiene": "improve" if "trace" in rule.name or "leakage" in rule.name else "unknown",
            "auto_promoted": False,
            "recommended_safe": high_safety,
        },
        risk_notes=[] if high_safety else ["Manual review required before production activation."],
    )


def enqueue_repair_candidates(candidates: list[RepairRule] | list[dict[str, Any]], source_run_id: str | None = None) -> list[dict[str, Any]]:
    ensure_dirs()
    queued: list[dict[str, Any]] = []
    for index, raw in enumerate(candidates):
        rule = raw if isinstance(raw, RepairRule) else rule_from_dict(raw)
        candidate = _candidate_from_rule(rule, source_run_id, index)
        write_json(_candidate_path(candidate.candidate_id), candidate.to_dict())
        queued.append(candidate.to_dict())
        append_repair_audit_event(
            "candidate_created",
            candidate_id=candidate.candidate_id,
            rule_id=rule.rule_id,
            details={"source_run_id": source_run_id, "severity": rule.severity, "auto_promoted": False},
        )
    return queued


def list_repair_candidates(status: str | None = None) -> list[dict[str, Any]]:
    ensure_dirs()
    rows: list[dict[str, Any]] = []
    for path in sorted((SURFACE_ROOT / "review_queue").glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = read_json(path, None)
        if not isinstance(payload, dict):
            continue
        if status and payload.get("status") != status:
            continue
        rows.append(payload)
    return rows


def get_repair_candidate(candidate_id: str) -> dict[str, Any]:
    payload = read_json(_candidate_path(candidate_id), None)
    if not isinstance(payload, dict):
        raise KeyError(f"repair candidate not found: {candidate_id}")
    return payload


def _save_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    write_json(_candidate_path(str(candidate["candidate_id"])), candidate)
    copy_dir = _status_copy_dir(str(candidate.get("status")))
    if copy_dir:
        copy_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_candidate_path(str(candidate["candidate_id"])), copy_dir / f"{candidate['candidate_id']}.json")
    return candidate


def approve_repair_candidate(candidate_id: str, reviewer: str = "local_operator", comment: str | None = None) -> dict[str, Any]:
    candidate = get_repair_candidate(candidate_id)
    rule = rule_from_dict(candidate.get("proposed_rule") or {})
    production_rule = upsert_production_rule(rule, candidate_id=candidate_id, approved_by=reviewer)
    candidate["status"] = "approved"
    candidate["review"] = {
        "reviewed_at": utc_now_iso(),
        "reviewer": reviewer,
        "decision": "approved",
        "comment": comment,
    }
    candidate["production_rule_id"] = production_rule.get("rule_id")
    _save_candidate(candidate)
    append_repair_audit_event("candidate_approved", candidate_id=candidate_id, rule_id=rule.rule_id, actor=reviewer, details={"comment": comment})
    return production_rule


def reject_repair_candidate(candidate_id: str, reviewer: str = "local_operator", comment: str | None = None) -> dict[str, Any]:
    candidate = get_repair_candidate(candidate_id)
    rule_id = str((candidate.get("proposed_rule") or {}).get("rule_id") or "")
    candidate["status"] = "rejected"
    candidate["review"] = {
        "reviewed_at": utc_now_iso(),
        "reviewer": reviewer,
        "decision": "rejected",
        "comment": comment,
    }
    _save_candidate(candidate)
    append_repair_audit_event("candidate_rejected", candidate_id=candidate_id, rule_id=rule_id or None, actor=reviewer, details={"comment": comment})
    return candidate


def archive_repair_candidate(candidate_id: str) -> dict[str, Any]:
    candidate = get_repair_candidate(candidate_id)
    rule_id = str((candidate.get("proposed_rule") or {}).get("rule_id") or "")
    candidate["status"] = "archived"
    _save_candidate(candidate)
    append_repair_audit_event("candidate_archived", candidate_id=candidate_id, rule_id=rule_id or None)
    return candidate


def edit_repair_candidate(
    candidate_id: str,
    patch: dict[str, Any],
    *,
    editor: str = "local_operator",
) -> dict[str, Any]:
    candidate = get_repair_candidate(candidate_id)
    proposed = dict(candidate.get("proposed_rule") or {})
    if "proposed_rule" in patch and isinstance(patch["proposed_rule"], dict):
        proposed.update(patch["proposed_rule"])
    for key in ("reason", "example_before", "example_after", "expected_effect", "risk_notes", "severity"):
        if key in patch:
            candidate[key] = patch[key]
    candidate["proposed_rule"] = rule_from_dict(proposed).to_dict()
    candidate["status"] = str(patch.get("status") or "needs_edit")
    _save_candidate(candidate)
    append_repair_audit_event(
        "candidate_edited",
        candidate_id=candidate_id,
        rule_id=candidate["proposed_rule"].get("rule_id"),
        actor=editor,
        details={"patch_keys": sorted(patch.keys())},
    )
    return candidate
