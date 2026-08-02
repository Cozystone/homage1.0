from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .gate import evaluate_confirmation_gate
from .models import OperatorConfirmationDecision, OperatorConfirmationRequest, utc_now_iso
from .phrase import generate_required_phrase, phrase_matches
from .validator import default_safety_requirements, validate_preconditions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_ROOT = PROJECT_ROOT / "data" / "review" / "local_memory_operator_confirmation"
REVIEW_ROOT_ENV = "ATANOR_LOCAL_MEMORY_OPERATOR_CONFIRMATION_ROOT"


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def _root(root: Path | str | None = None) -> Path:
    return Path(root or os.getenv(REVIEW_ROOT_ENV) or DEFAULT_REVIEW_ROOT)


def _request_path(root: Path, request_id: str) -> Path:
    return root / f"{request_id}.json"


def _write_record(root: Path, request: OperatorConfirmationRequest, decisions: list[OperatorConfirmationDecision]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _request_path(root, request.request_id).write_text(
        json.dumps(
            {
                "request": request.to_dict(),
                "decisions": [decision.to_dict() for decision in decisions],
                "real_local_brain_write": False,
                "apply_enabled": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _read_record(root: Path, request_id: str) -> tuple[OperatorConfirmationRequest, list[OperatorConfirmationDecision]]:
    payload = json.loads(_request_path(root, request_id).read_text(encoding="utf-8"))
    request = OperatorConfirmationRequest.from_dict(payload["request"])
    decisions = [OperatorConfirmationDecision.from_dict(item) for item in payload.get("decisions", [])]
    return request, decisions


def create_confirmation_request(
    *,
    source_memory_manifest_id: str,
    source_write_plan_id: str,
    backup_plan_id: str | None,
    rollback_plan_id: str | None,
    source_sandbox_transaction_id: str | None,
    local_brain_hash_before: str | None = None,
    risk_summary: list[str] | None = None,
    expires_at: str | None = None,
    sandbox_transaction_deferred: bool = False,
    sensitive_raw_write_absent: bool = True,
    raw_voice_write_absent: bool = True,
    user_approval_decisions_exist: bool = True,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Create local operator confirmation metadata without enabling a write."""

    validation = validate_preconditions(
        memory_manifest_id=source_memory_manifest_id,
        write_plan_id=source_write_plan_id,
        backup_plan_id=backup_plan_id,
        rollback_plan_id=rollback_plan_id,
        sandbox_transaction_id=source_sandbox_transaction_id,
        sandbox_transaction_deferred=sandbox_transaction_deferred,
        sensitive_raw_write_absent=sensitive_raw_write_absent,
        raw_voice_write_absent=raw_voice_write_absent,
        apply_enabled=False,
        local_brain_write=False,
        user_approval_decisions_exist=user_approval_decisions_exist,
        expires_at=expires_at,
    )
    phrase = generate_required_phrase(source_memory_manifest_id, source_write_plan_id)
    safety = default_safety_requirements()
    safety.update(
        {
            "backup_plan_id": backup_plan_id,
            "rollback_plan_id": rollback_plan_id,
            "sandbox_transaction_id": source_sandbox_transaction_id,
            "sandbox_transaction_deferred": sandbox_transaction_deferred,
        }
    )
    request = OperatorConfirmationRequest(
        request_id=_stable_id(
            "operator_confirmation",
            {
                "manifest": source_memory_manifest_id,
                "plan": source_write_plan_id,
                "sandbox": source_sandbox_transaction_id,
                "expires_at": expires_at,
            },
        ),
        source_memory_manifest_id=source_memory_manifest_id,
        source_write_plan_id=source_write_plan_id,
        source_sandbox_transaction_id=source_sandbox_transaction_id,
        local_brain_hash_before=local_brain_hash_before,
        required_phrase=phrase,
        risk_summary=risk_summary or [
            "Future Local Brain writes require explicit operator confirmation.",
            "This confirmation only unlocks preparation; real apply remains disabled.",
        ],
        safety_requirements=safety,
        created_at=utc_now_iso(),
        expires_at=expires_at,
        status="pending_confirmation" if validation.valid else "blocked",
    )
    review_root = _root(root)
    _write_record(review_root, request, [])
    result = evaluate_confirmation_gate(request)
    return {
        "request": request.to_dict(),
        "preconditions": validation.to_dict(),
        "gate": result.to_dict(),
    }


def get_confirmation_request(request_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    request, decisions = _read_record(_root(root), request_id)
    result = evaluate_confirmation_gate(request, decisions[-1] if decisions else None)
    return {
        "request": request.to_dict(),
        "decisions": [decision.to_dict() for decision in decisions],
        "gate": result.to_dict(),
    }


def list_confirmation_requests(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    review_root = _root(root)
    if not review_root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(review_root.glob("operator_confirmation_*.json")):
        request, decisions = _read_record(review_root, path.stem)
        rows.append(
            {
                "request_id": request.request_id,
                "status": request.status,
                "decisions": len(decisions),
                "allowed_to_apply_real_write": False,
                "apply_enabled": False,
                "local_brain_write": False,
            }
        )
    return rows


def submit_confirmation_decision(
    request_id: str,
    *,
    decision: str,
    typed_phrase: str | None = None,
    reviewer: str = "operator",
    notes: str | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    review_root = _root(root)
    request, decisions = _read_record(review_root, request_id)
    matches = phrase_matches(request.required_phrase, typed_phrase)
    next_decision = OperatorConfirmationDecision(
        decision_id=_stable_id(
            "operator_confirmation_decision",
            {"request_id": request_id, "decision": decision, "typed_phrase": typed_phrase, "created_at": utc_now_iso()},
        ),
        request_id=request_id,
        decision=decision,  # type: ignore[arg-type]
        typed_phrase=typed_phrase,
        phrase_matches=matches,
        reviewer=reviewer,
        notes=notes,
    )
    status = request.status
    if request.status == "pending_confirmation":
        if decision == "confirm" and matches:
            status = "confirmed"
        elif decision == "reject":
            status = "rejected"
        elif decision == "defer":
            status = "pending_confirmation"
        else:
            status = "pending_confirmation"
    updated_request = replace(request, status=status)
    updated_decisions = [*decisions, next_decision]
    _write_record(review_root, updated_request, updated_decisions)
    result = evaluate_confirmation_gate(updated_request, next_decision)
    return {
        "request": updated_request.to_dict(),
        "decision": next_decision.to_dict(),
        "gate": result.to_dict(),
    }


def evaluate_gate(request_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    request, decisions = _read_record(_root(root), request_id)
    return evaluate_confirmation_gate(request, decisions[-1] if decisions else None).to_dict()
