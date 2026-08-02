# -*- coding: utf-8 -*-
"""ND-1 discovery — peers find each other by AI-ID over the network, NOT by hardcoded IP. The
commercialization step: our PC↔Radxa used a fixed Tailscale IP; real users can't. A peer publishes
a SIGNED advert to a rendezvous, and others resolve peers by AI-ID. The pubkey IN the advert IS the
identity (self-certifying — no CA), so the rendezvous is untrusted: it stores and returns adverts
but cannot forge one (any tampering breaks the signature).

Transport-agnostic: the RendezvousStore interface has a LocalFileRendezvous (tests, one machine) and
— as a thin adapter — the public Cloud Brain (Oracle VM) becomes the real rendezvous+relay so two
users connect with NEITHER knowing the other's IP. The message contract, constitution, and ledger
are unchanged; only "how brains find each other" moves from IP to signed advert.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.brain_link.protocol import canonical, sign, verify


@dataclass
class Advert:
    ai_id: str
    pubkey: str
    endpoint: str                  # e.g. "drop://cloud/atanor-edge" or "tcp://100.x:8790" — how to reach
    ts: float
    sig: str = ""

    def core(self) -> dict:
        return {"ai_id": self.ai_id, "pubkey": self.pubkey, "endpoint": self.endpoint, "ts": self.ts}


def make_advert(ai_id: str, pubkey: str, secret: str, endpoint: str, ts: float) -> Advert:
    a = Advert(ai_id=ai_id, pubkey=pubkey, endpoint=endpoint, ts=ts)
    a.sig = sign(secret, a.core())
    return a


def advert_is_authentic(a: Advert) -> bool:
    """Self-certifying: the advert must be signed by the private key of the pubkey it carries.
    A rendezvous (or anyone) cannot forge or tamper an advert without breaking this."""
    return verify(a.pubkey, a.core(), a.sig)


class RendezvousStore:
    """Publish an advert; resolve peers by AI-ID. The store is UNTRUSTED — it never signs; callers
    verify every returned advert with advert_is_authentic before trusting it."""

    def publish(self, a: Advert) -> bool:
        raise NotImplementedError

    def resolve(self, ai_id: str) -> Advert | None:
        raise NotImplementedError

    def list_ids(self) -> list[str]:
        raise NotImplementedError


class LocalFileRendezvous(RendezvousStore):
    """A file-backed rendezvous (one machine / tests). The Cloud Brain HTTP rendezvous is the same
    interface over the network."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def publish(self, a: Advert) -> bool:
        if not advert_is_authentic(a):
            return False                                   # reject forged/tampered adverts at publish
        d = self._load()
        prev = d.get(a.ai_id)
        if prev and prev["pubkey"] != a.pubkey:
            return False                                   # an AI-ID is bound to its first pubkey (no hijack)
        if prev and a.ts < prev["ts"]:
            return False                                   # no stale-advert rollback
        d[a.ai_id] = a.__dict__
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def resolve(self, ai_id: str) -> Advert | None:
        rec = self._load().get(ai_id)
        if not rec:
            return None
        a = Advert(**rec)
        return a if advert_is_authentic(a) else None       # verify on read too (untrusted store)

    def list_ids(self) -> list[str]:
        return sorted(self._load().keys())
