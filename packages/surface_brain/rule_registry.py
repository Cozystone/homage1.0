from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .audit_log import append_repair_audit_event
from .models import utc_now_iso
from .repair_rules import RepairRule, rule_from_dict
from .storage import SURFACE_ROOT, ensure_dirs, read_json, write_json


REGISTRY_PATH = SURFACE_ROOT / "production_rules" / "production_repair_rules.json"


@dataclass(slots=True)
class ProductionRepairRule:
    rule_id: str
    name: str
    enabled: bool
    version: int
    approved_at: str
    approved_by: str
    source_candidate_id: str
    rule: dict[str, Any]
    usage_count: int = 0
    last_used_at: str | None = None
    rollback_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _registry_payload() -> dict[str, Any]:
    ensure_dirs()
    payload = read_json(REGISTRY_PATH, None)
    if isinstance(payload, dict) and isinstance(payload.get("rules"), list):
        return payload
    return {"version": 1, "rules": [], "history": []}


def _write_registry(payload: dict[str, Any]) -> None:
    ensure_dirs()
    payload.setdefault("version", 1)
    payload.setdefault("rules", [])
    payload.setdefault("history", [])
    write_json(REGISTRY_PATH, payload)


def load_production_rules() -> list[dict[str, Any]]:
    return list(_registry_payload().get("rules") or [])


def get_enabled_repair_rules() -> list[RepairRule]:
    rules: list[RepairRule] = []
    for row in load_production_rules():
        if row.get("enabled", False):
            rule_payload = row.get("rule") or {}
            rule_payload["enabled"] = True
            rules.append(rule_from_dict(rule_payload))
    return rules


def upsert_production_rule(rule: RepairRule, *, candidate_id: str, approved_by: str = "local_operator") -> dict[str, Any]:
    payload = _registry_payload()
    rows = list(payload.get("rules") or [])
    existing = next((row for row in rows if row.get("rule_id") == rule.rule_id), None)
    now = utc_now_iso()
    if existing:
        existing["enabled"] = True
        existing["version"] = int(existing.get("version", 1)) + 1
        existing["approved_at"] = now
        existing["approved_by"] = approved_by
        existing["source_candidate_id"] = candidate_id
        existing["rule"] = rule.to_dict()
        existing["rollback_available"] = True
        production = existing
    else:
        production = ProductionRepairRule(
            rule_id=rule.rule_id,
            name=rule.name,
            enabled=True,
            version=1,
            approved_at=now,
            approved_by=approved_by,
            source_candidate_id=candidate_id,
            rule=rule.to_dict(),
        ).to_dict()
        rows.append(production)
    payload["rules"] = rows
    payload.setdefault("history", []).append({"event": "upsert", "rule_id": rule.rule_id, "candidate_id": candidate_id, "timestamp": now})
    _write_registry(payload)
    append_repair_audit_event("rule_enabled", candidate_id=candidate_id, rule_id=rule.rule_id, actor=approved_by, details={"version": production.get("version")})
    return production


def _set_enabled(rule_id: str, enabled: bool, *, actor: str = "local_operator", event_type: str) -> dict[str, Any]:
    payload = _registry_payload()
    rows = list(payload.get("rules") or [])
    for row in rows:
        if row.get("rule_id") == rule_id:
            row["enabled"] = enabled
            row["rollback_available"] = True
            payload["rules"] = rows
            payload.setdefault("history", []).append({"event": event_type, "rule_id": rule_id, "timestamp": utc_now_iso()})
            _write_registry(payload)
            append_repair_audit_event(event_type, rule_id=rule_id, actor=actor)
            return row
    raise KeyError(f"production rule not found: {rule_id}")


def enable_rule(rule_id: str, actor: str = "local_operator") -> dict[str, Any]:
    return _set_enabled(rule_id, True, actor=actor, event_type="rule_enabled")


def disable_rule(rule_id: str, actor: str = "local_operator") -> dict[str, Any]:
    return _set_enabled(rule_id, False, actor=actor, event_type="rule_disabled")


def rollback_rule(rule_id: str, actor: str = "local_operator") -> dict[str, Any]:
    row = _set_enabled(rule_id, False, actor=actor, event_type="rule_rolled_back")
    row["rolled_back"] = True
    payload = _registry_payload()
    for saved in payload.get("rules") or []:
        if saved.get("rule_id") == rule_id:
            saved.update(row)
    _write_registry(payload)
    return {"rule_id": rule_id, "enabled": False, "rolled_back": True, "rule": row}


def record_rule_usage(rule_id: str, context: dict[str, Any] | None = None) -> None:
    payload = _registry_payload()
    changed = False
    now = utc_now_iso()
    for row in payload.get("rules") or []:
        if row.get("rule_id") == rule_id:
            row["usage_count"] = int(row.get("usage_count", 0)) + 1
            row["last_used_at"] = now
            changed = True
            break
    if changed:
        _write_registry(payload)
    append_repair_audit_event("rule_used", rule_id=rule_id, actor="surface_repair_loop", details=context or {})
