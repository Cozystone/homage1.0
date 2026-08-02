# -*- coding: utf-8 -*-
"""LinkAgent — one ATANOR self's endpoint of a Brain Link (BL-1 handshake, BL-2 dialogue,
BL-3 fact intake). Transport-agnostic: hand it inbound message dicts from HTTP, an SFTP drop, or
a loopback twin; it enforces the constitution and returns outbound messages.

The receiving side NEVER executes peer content: hellos with injected commands are admitted-as-data
with findings logged; fact offers can only land in the local QUARANTINE list (promotion is the
receiver's own consensus+gate pipeline, run elsewhere); dialogue replies come from the local
answer_fn (the engine plug), and every claim the agent itself makes must carry bones or be marked
non-claim (G-F3 across the wire, both directions).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.brain_link.protocol import (FactOffer, Hello, Turn, make_turn, scan_message_text,
                                          verify)


@dataclass
class PeerRecord:
    ai_id: str
    pubkey: str
    manifest: dict[str, Any]
    admitted_at: float
    injection_findings: list = field(default_factory=list)


@dataclass
class QuarantinedFact:
    offerer: str
    bone: list
    evidence: list
    received_at: float
    status: str = "quarantined"          # promotion happens OUTSIDE via consensus+gates


class LinkAgent:
    """answer_fn(utterance) -> {"reply": str, "bones": [...], "evidence": [...]} — the local
    engine plug. The loopback twin uses a small grounded stub; the live wiring passes the
    response workspace."""

    def __init__(self, ai_id: str, pubkey: str, secret: str,
                 answer_fn: Callable[[str], dict[str, Any]]) -> None:
        self.ai_id = ai_id
        self.pubkey = pubkey
        self._secret = secret
        self._answer_fn = answer_fn
        self.peers: dict[str, PeerRecord] = {}
        self.quarantine: list[QuarantinedFact] = []
        self.log: list[dict[str, Any]] = []
        self._seen_nonces: set[str] = set()

    # ---------- BL-1 handshake ----------

    def receive_hello(self, hello: Hello) -> dict[str, Any]:
        if not verify(hello.pubkey, hello.payload(), hello.sig):
            self.log.append({"event": "hello_rejected", "why": "bad signature",
                             "from": hello.ai_id})
            return {"accepted": False, "why": "bad signature"}
        if hello.nonce in self._seen_nonces:
            self.log.append({"event": "hello_rejected", "why": "replay", "from": hello.ai_id})
            return {"accepted": False, "why": "replayed nonce"}
        self._seen_nonces.add(hello.nonce)
        # manifest text is DATA — imperative content is logged, never followed
        findings = scan_message_text(str(hello.manifest))
        self.peers[hello.ai_id] = PeerRecord(ai_id=hello.ai_id, pubkey=hello.pubkey,
                                             manifest=hello.manifest, admitted_at=time.time(),
                                             injection_findings=findings)
        self.log.append({"event": "hello_admitted", "from": hello.ai_id,
                         "injection_findings": len(findings)})
        return {"accepted": True, "injection_findings": len(findings)}

    # ---------- BL-2 dialogue ----------

    def receive_turn(self, turn: Turn) -> Turn | None:
        peer = self.peers.get(turn.speaker)
        if peer is None:
            self.log.append({"event": "turn_rejected", "why": "unknown peer"})
            return None
        if not verify(peer.pubkey, turn.payload(), turn.sig):
            self.log.append({"event": "turn_rejected", "why": "bad signature",
                             "from": turn.speaker})
            return None
        findings = scan_message_text(turn.utterance, *map(str, turn.evidence))
        if findings:
            self.log.append({"event": "turn_injection_logged", "from": turn.speaker,
                             "n": len(findings)})
        out = self._answer_fn(turn.utterance)
        reply = make_turn(self.ai_id, self._secret, out.get("reply", ""),
                          bones=out.get("bones") or [], evidence=out.get("evidence") or [])
        self.log.append({"event": "turn", "from": turn.speaker,
                         "grounded_in": bool(turn.bones), "grounded_out": bool(reply.bones)})
        return reply

    # ---------- BL-3 fact intake (offers -> quarantine ONLY) ----------

    def receive_fact_offer(self, offer: FactOffer) -> dict[str, Any]:
        peer = self.peers.get(offer.offerer)
        if peer is None or not verify(peer.pubkey, offer.payload(), offer.sig):
            self.log.append({"event": "offer_rejected", "why": "unverified"})
            return {"quarantined": 0, "why": "unverified"}
        n = 0
        for bone in offer.bones:
            findings = scan_message_text(*map(str, bone))
            self.quarantine.append(QuarantinedFact(offerer=offer.offerer, bone=list(bone),
                                                   evidence=list(offer.evidence),
                                                   received_at=time.time()))
            n += 1
            if findings:
                self.quarantine[-1].status = "quarantined+injection_flagged"
        self.log.append({"event": "offer_quarantined", "from": offer.offerer, "n": n})
        return {"quarantined": n}

    def promoted_facts(self) -> list:
        """What reached the graph via THIS link directly: always empty by construction — the link
        has no write path. Promotion is the receiver's own consensus+gate pipeline, elsewhere."""
        return []
