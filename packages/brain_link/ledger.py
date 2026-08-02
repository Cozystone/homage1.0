# -*- coding: utf-8 -*-
"""Brain Link ledger — a hash-chained, signed, tamper-EVIDENT log of what agents exchanged. This is
the doctrine-correct core of the "blockchain for Brain Link" idea: it makes the AUDIT TRAIL
immutable, so no peer can silently rewrite past dialogue, evidence, or knowledge offers.

What it deliberately is NOT (the corrections to a naive on-chain design):
  - NOT an immutable knowledge graph. Our knowledge must stay CORRECTABLE (retract / as_of /
    word-sense tombstones). Only the RECORD of an exchange is immutable, never the facts themselves;
    a retraction is itself a new, chained entry — history is append-only, truth is revisable.
  - NOT an on-chain constitution. auto_self_modification / patch_intake are enforced LOCALLY and are
    immutable BY DESIGN (genesis immunity). Putting the gate where network consensus could alter it
    would DESTROY that immutability. The ledger may RECORD "a gate passed at hash X"; it must never
    BE the gate.
  - NOT proof-of-work / a heavy consensus chain. A federation of cryptographically-identified,
    revocably-trusted peers (peer_trust_guard) needs tamper-evidence, not mining. A signed hash
    chain (each entry references the prior hash; each actor signs its own entries) gives exactly
    that at ~zero cost — the "lightweight DAG ledger" done honestly.

Verification is total-order over a single node's chain; for N nodes each keeps its own chain and
they cross-reference each other's tip hashes on handshake (a lattice of signed chains, not one
global chain requiring consensus). That preserves the solidarity-growth doctrine: every node reads
equally; only tamper-evidence, not a central authority, is added.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.brain_link.protocol import canonical, sign, verify

GENESIS = "0" * 64


def _hash(entry_core: dict) -> str:
    return hashlib.sha256(canonical(entry_core).encode("utf-8")).hexdigest()


@dataclass
class Entry:
    seq: int
    ts: float
    actor: str                     # ai_id of who recorded this
    kind: str                      # hello | turn | fact_offer | gate_pass | retract
    payload_hash: str              # sha256 of the exchanged content (content stored elsewhere)
    prev_hash: str
    this_hash: str = ""
    sig: str = ""

    def core(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "actor": self.actor, "kind": self.kind,
                "payload_hash": self.payload_hash, "prev_hash": self.prev_hash}


class Ledger:
    """One node's append-only signed hash chain over its Brain Link exchanges."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.entries: list[Entry] = []
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    self.entries.append(Entry(**d))

    def tip(self) -> str:
        return self.entries[-1].this_hash if self.entries else GENESIS

    @staticmethod
    def payload_hash(content: Any) -> str:
        return hashlib.sha256(canonical({"c": content}).encode("utf-8")).hexdigest()

    def append(self, actor: str, kind: str, content: Any, secret: str, ts: float) -> Entry:
        e = Entry(seq=len(self.entries), ts=ts, actor=actor, kind=kind,
                  payload_hash=self.payload_hash(content), prev_hash=self.tip())
        e.this_hash = _hash(e.core())
        e.sig = sign(secret, {"h": e.this_hash})           # the actor signs the entry hash
        self.entries.append(e)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(e.__dict__, ensure_ascii=False) + "\n")
        return e

    def verify(self, pubkeys: dict[str, str] | None = None) -> dict[str, Any]:
        """Recompute the chain. Returns {ok, broken_at, reason}. Any altered past entry breaks its
        hash (and every subsequent prev_hash link) and/or its signature — tamper is DETECTED, not
        preventable, which is the honest guarantee."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i:
                return {"ok": False, "broken_at": i, "reason": f"seq {e.seq} != index {i}"}
            if e.prev_hash != prev:
                return {"ok": False, "broken_at": i, "reason": "prev_hash breaks the chain"}
            if _hash(e.core()) != e.this_hash:
                return {"ok": False, "broken_at": i, "reason": "content tampered (hash mismatch)"}
            if pubkeys is not None:
                pk = pubkeys.get(e.actor)
                if pk is None or not verify(pk, {"h": e.this_hash}, e.sig):
                    return {"ok": False, "broken_at": i, "reason": "signature invalid for actor"}
            prev = e.this_hash
        return {"ok": True, "broken_at": None, "reason": "chain intact", "length": len(self.entries)}
