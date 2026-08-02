from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_HOST_AUDIT_LOG_PATH = Path("runtime/agentic_micro_os/host_authority_audit.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class HostAuditLog:
    path: Path = DEFAULT_HOST_AUDIT_LOG_PATH

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "ts": utc_now_iso(),
            "event": event,
            **payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def status(self) -> dict[str, str | bool]:
        return {
            "audit_log_path": str(self.path),
            "audit_log_exists": self.path.exists(),
        }
