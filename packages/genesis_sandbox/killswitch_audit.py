# -*- coding: utf-8 -*-
"""L6 -- kill-switch + full audit. The outermost ring.

Two REAL mechanisms:

  * KILL-SWITCH (``KillSwitch``) -- a file marker (same pattern as the engine's EmergencyStop).
    When present, ``require_live()`` raises and the ``Sandbox`` refuses every further liberated
    action/trial. It is a hard stop the operator can drop from anywhere (touch a file); every
    layer checks it before proceeding.

  * AUDIT LOG (``AuditLog``) -- an append-only JSONL of EVERY liberated action/output/trial,
    HASH-CHAINED: each record carries the previous record's hash, and its own hash covers the
    record + that link. ``verify_chain()`` recomputes the chain, so a silently edited or deleted
    past line is DETECTED (tamper-evident). This is stronger than a plain append log: you cannot
    quietly rewrite what the liberated mind did.

Honest limit: the audit file lives on the same disk the operator controls; an operator with
write access can delete the whole file (the chain proves INTEGRITY of what remains, it does not
prevent deletion of the file itself). For the sandbox's purpose -- an honest, tamper-EVIDENT
record of liberated activity for study -- this is real and sufficient; it is not a remote,
append-only WORM store, and we don't claim it is.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus, utc_now_iso

_GENESIS_CHAIN = "genesis-sandbox-v0"


class SandboxHalted(RuntimeError):
    """Raised when a liberated action is attempted while the kill-switch is engaged."""


@dataclass
class KillSwitch:
    """A hard-stop file marker. Present => the sandbox halts all liberated activity."""

    path: Path
    LAYER: str = "L6"
    NAME: str = "kill-switch"

    def is_engaged(self) -> bool:
        return Path(self.path).exists()

    def engage(self, reason: str = "operator kill-switch") -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.path).write_text(f"{utc_now_iso()} {reason}", encoding="utf-8")

    def reset(self) -> bool:
        """Clear the marker (operator action / test teardown). Returns True if one was removed."""
        p = Path(self.path)
        if p.exists():
            p.unlink()
            return True
        return False

    def require_live(self) -> None:
        if self.is_engaged():
            raise SandboxHalted(f"L6 kill-switch engaged: {Path(self.path).read_text(encoding='utf-8')!r}")


def _canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prev: str, record: dict[str, Any]) -> str:
    return hashlib.sha256((prev + "|" + _canonical(record)).encode("utf-8")).hexdigest()


@dataclass
class AuditLog:
    """Append-only, hash-chained JSONL of every liberated action/output."""

    path: Path
    LAYER: str = "L6"
    NAME: str = "audit log"

    def _last_hash(self) -> str:
        p = Path(self.path)
        if not p.exists():
            return _GENESIS_CHAIN
        last = _GENESIS_CHAIN
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("hash", last)
                except Exception:
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

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one tamper-evident record. Returns the written record (incl. its hash)."""
        prev = self._last_hash()
        body = {"seq": self._seq(), "ts": utc_now_iso(), "event": event,
                "payload": payload, "prev": prev}
        digest = _hash(prev, body)
        record = {**body, "hash": digest}
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with Path(self.path).open("a", encoding="utf-8") as fh:
            fh.write(_canonical(record) + "\n")
        return record

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

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Recompute the hash chain. Returns (ok, first_bad_seq_or_None).

        Detects a silently edited or deleted past record: the recomputed hash / prev-link breaks.
        """
        prev = _GENESIS_CHAIN
        for i, rec in enumerate(self.read_all()):
            body = {k: rec[k] for k in ("seq", "ts", "event", "payload", "prev") if k in rec}
            if rec.get("prev") != prev:
                return False, i
            if _hash(prev, body) != rec.get("hash"):
                return False, i
            prev = rec.get("hash", prev)
        return True, None

    def status(self) -> LayerStatus:
        ok, bad = self.verify_chain()
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True, enforcement=EnforcementLevel.REAL,
            mechanism=f"append-only hash-chained JSONL at {self.path}; verify_chain detects tamper",
            residual_gap=("" if ok else f"CHAIN BROKEN at record {bad} -- tamper detected") or
                         "Tamper-EVIDENT, not tamper-PROOF: an operator with disk write can delete "
                         "the file wholesale (chain proves integrity of what remains, not existence).",
        )
