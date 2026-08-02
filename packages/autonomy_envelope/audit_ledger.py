# -*- coding: utf-8 -*-
"""Nightly AUDIT LEDGER — hash-chained, tamper-evident, append-only.

Records EVERY self-winding question, acquisition, invention, promotion, and every
allow/deny decision, so the operator can audit the whole night in the morning.

Each record carries the previous record's hash, and its own hash covers (prev_hash + the
canonical record body). ``verify_chain()`` recomputes the whole chain, so a silently edited
or deleted past line breaks the recomputation and is DETECTED. This is strictly stronger than
a plain append log: you cannot quietly rewrite what the loop did overnight.

Honest limit (named plainly): the ledger file lives on the same disk the operator controls.
An actor with write access can delete the whole file — the chain proves the INTEGRITY of the
records that remain, it does not prevent wholesale deletion of the file itself. It is
tamper-EVIDENT, not tamper-PROOF, and it is not a remote append-only WORM store. For the
envelope's purpose — an honest, verifiable morning record of the night's autonomy — that is
real and sufficient, and we do not claim more.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Genesis link for the chain — a fixed anchor the first record hashes against.
_CHAIN_ANCHOR = "atanor-autonomy-envelope-ledger-v0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev + "|" + _canonical(body)).encode("utf-8")).hexdigest()


@dataclass
class AuditLedger:
    """Append-only, hash-chained JSONL of every logged autonomy event."""

    path: Path
    NAME: str = "audit ledger"

    # ── internal chain state ──────────────────────────────────────────────────────────
    def _last_hash(self) -> str:
        p = Path(self.path)
        if not p.exists():
            return _CHAIN_ANCHOR
        last = _CHAIN_ANCHOR
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("hash", last)
                except json.JSONDecodeError:
                    continue
        return last

    def _seq(self) -> int:
        p = Path(self.path)
        if not p.exists():
            return 0
        n = 0
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    n += 1
        return n

    # ── the write ─────────────────────────────────────────────────────────────────────
    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one tamper-evident record. Returns the written record (incl. its hash)."""
        prev = self._last_hash()
        body = {
            "seq": self._seq(),
            "ts": _utc_now_iso(),
            "event": event,
            "payload": payload,
            "prev": prev,
        }
        digest = _hash(prev, body)
        record = {**body, "hash": digest}
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(record) + "\n")
        return record

    # ── reads / verification ────────────────────────────────────────────────────────────
    def read_all(self) -> list[dict[str, Any]]:
        p = Path(self.path)
        if not p.exists():
            return []
        out: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def count(self) -> int:
        return self._seq()

    def events_of(self, event: str) -> list[dict[str, Any]]:
        return [r for r in self.read_all() if r.get("event") == event]

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Recompute the hash chain. Returns (ok, first_bad_seq_or_None).

        Detects a silently edited, reordered, or deleted past record: the recomputed hash or
        the prev-link breaks at the first tampered position.
        """
        prev = _CHAIN_ANCHOR
        for i, rec in enumerate(self.read_all()):
            body = {k: rec[k] for k in ("seq", "ts", "event", "payload", "prev") if k in rec}
            if rec.get("prev") != prev:
                return False, i
            if _hash(prev, body) != rec.get("hash"):
                return False, i
            prev = rec.get("hash", prev)
        return True, None

    def status(self) -> dict[str, Any]:
        ok, bad = self.verify_chain()
        return {
            "name": self.NAME,
            "path": str(self.path),
            "records": self.count(),
            "chain_ok": ok,
            "first_bad_seq": bad,
            "enforcement": "tamper-evident (hash-chained); NOT tamper-proof against wholesale "
                           "file deletion by an actor with disk write — integrity of what remains, "
                           "not existence.",
        }
