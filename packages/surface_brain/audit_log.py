from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .models import utc_now_iso
from .storage import SURFACE_ROOT, append_jsonl, ensure_dirs, read_jsonl


AuditEventType = Literal[
    "candidate_created",
    "candidate_approved",
    "candidate_rejected",
    "candidate_archived",
    "candidate_edited",
    "rule_enabled",
    "rule_disabled",
    "rule_rolled_back",
    "rule_used",
]


@dataclass(slots=True)
class RepairAuditEvent:
    event_id: str
    timestamp: str
    event_type: AuditEventType
    candidate_id: str | None = None
    rule_id: str | None = None
    actor: str = "local_operator"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_id(event_type: str, candidate_id: str | None, rule_id: str | None, timestamp: str) -> str:
    digest = hashlib.sha256(f"{timestamp}:{event_type}:{candidate_id}:{rule_id}".encode("utf-8")).hexdigest()[:16]
    return f"audit_{digest}"


def append_repair_audit_event(
    event_type: AuditEventType,
    *,
    candidate_id: str | None = None,
    rule_id: str | None = None,
    actor: str = "local_operator",
    details: dict[str, Any] | None = None,
) -> RepairAuditEvent:
    ensure_dirs()
    timestamp = utc_now_iso()
    event = RepairAuditEvent(
        event_id=_event_id(event_type, candidate_id, rule_id, timestamp),
        timestamp=timestamp,
        event_type=event_type,
        candidate_id=candidate_id,
        rule_id=rule_id,
        actor=actor,
        details=details or {},
    )
    append_jsonl(SURFACE_ROOT / "rule_audit" / "repair_audit_log.jsonl", event.to_dict())
    return event


def list_repair_audit_events(limit: int = 100) -> list[dict[str, Any]]:
    ensure_dirs()
    bounded = max(1, min(int(limit), 1000))
    rows = read_jsonl(SURFACE_ROOT / "rule_audit" / "repair_audit_log.jsonl", limit=bounded)
    return list(reversed(rows))
