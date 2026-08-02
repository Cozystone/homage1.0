#!/usr/bin/env python3
"""File-based Claude<->Codex orchestration mailbox (robust, no UI / no Computer Use).

The fragile part of the old loop was Codex puppeting Claude Desktop's UI via
Computer Use (window focus on Windows keeps failing). This replaces that channel
with a deterministic shared-filesystem mailbox both agents can read/write:

  orchestration/requests/   REQ-<id>.json   (Claude files an approval/review request)
  orchestration/responses/  RESP-<id>.json  (Codex files the verdict)

Risk tiers (who may approve):
  - "auto_ok"      : reversible/local RED -> Codex may verdict=approve
  - "operator_only": irreversible/external (push/PR/deploy/publish/perm/delete)
                     -> Codex MUST verdict=escalate; only the human operator decides

Usage:
  request   --action ... --files ... --tier auto_ok|operator_only --question ...
  list-pending                         (REQs with no response yet)
  respond   --id REQ-... --verdict approve|hold|escalate --notes ...
  check     --id REQ-...               (print response if any)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "orchestration"
REQ_DIR = ROOT / "requests"
RESP_DIR = ROOT / "responses"
VALID_TIERS = ("auto_ok", "operator_only")
VALID_VERDICTS = ("approve", "hold", "escalate")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    REQ_DIR.mkdir(parents=True, exist_ok=True)
    RESP_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, obj: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_request(action: str, files: str, tier: str, question: str) -> str:
    _ensure_dirs()
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be one of {VALID_TIERS}")
    req_id = "REQ-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{int(time.time()*1000)%1000:03d}"
    _atomic_write(REQ_DIR / f"{req_id}.json", {
        "id": req_id, "created_at": _now(), "from": "claude",
        "action": action, "files": files, "risk_tier": tier,
        "reversible": tier == "auto_ok", "question": question, "status": "pending",
    })
    return req_id


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_response(req_id: str) -> dict[str, Any] | None:
    p = RESP_DIR / f"RESP-{req_id}.json"
    return _load(p) if p.exists() else None


def pending_requests() -> list[dict[str, Any]]:
    _ensure_dirs()
    out = []
    for p in sorted(REQ_DIR.glob("REQ-*.json")):
        req = _load(p)
        if req and get_response(req.get("id", "")) is None:
            out.append(req)
    return out


def write_response(req_id: str, verdict: str, notes: str) -> None:
    _ensure_dirs()
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"verdict must be one of {VALID_VERDICTS}")
    req = _load(REQ_DIR / f"{req_id}.json")
    # safety: operator_only requests can never be auto-approved by the reviewer
    if req.get("risk_tier") == "operator_only" and verdict == "approve":
        verdict = "escalate"
        notes = "[auto-downgraded: operator_only tier cannot be reviewer-approved] " + notes
    _atomic_write(RESP_DIR / f"RESP-{req_id}.json", {
        "req_id": req_id, "responded_at": _now(), "from": "codex",
        "verdict": verdict, "notes": notes,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description="Claude<->Codex file mailbox")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("request")
    r.add_argument("--action", required=True)
    r.add_argument("--files", default="")
    r.add_argument("--tier", default="auto_ok", choices=VALID_TIERS)
    r.add_argument("--question", default="")
    sub.add_parser("list-pending")
    rp = sub.add_parser("respond")
    rp.add_argument("--id", required=True)
    rp.add_argument("--verdict", required=True, choices=VALID_VERDICTS)
    rp.add_argument("--notes", default="")
    c = sub.add_parser("check")
    c.add_argument("--id", required=True)
    args = ap.parse_args()

    if args.cmd == "request":
        print(write_request(args.action, args.files, args.tier, args.question))
    elif args.cmd == "list-pending":
        print(json.dumps(pending_requests(), ensure_ascii=False, indent=2))
    elif args.cmd == "respond":
        write_response(args.id, args.verdict, args.notes)
        print(f"RESP-{args.id} written")
    elif args.cmd == "check":
        print(json.dumps(get_response(args.id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
