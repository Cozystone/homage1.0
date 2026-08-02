# -*- coding: utf-8 -*-
"""Brain Link protocol — the AGENT-INTERACTION layer between two ATANOR selves (BL-1..BL-3).

Sits ON TOP of the existing identity/transport organs (brain_link_pool.peer_trust_guard: PoW,
signature, quarantine) and the injection boundary (graph_scale.injection_guard). This module owns
the message CONTRACT, and the contract carries the safety constitution in its shape:

  - HELLO carries a signed capability manifest — identity before conversation.
  - A dialogue TURN carries utterance + bones + evidence: every claim arrives with its grounding,
    so knowing/saying separation (G-F3) holds ACROSS the wire — an utterance with empty bones is
    a social move, never a fact.
  - A FACT OFFER is an offer, never a write: it can only enter the receiver's quarantine store;
    promotion needs the receiver's OWN consensus + promotion gates. A single peer is not consensus.
  - Everything inside peer messages is observed DATA: imperative content is detected (injection
    guard) and logged, never executed. Constitution files are not representable in the contract at
    all — there is no message type that ships code (genesis immunity extends to the network).

Signing: ed25519 when `cryptography` is present (peer_trust_guard.verify_signature's preferred
path), falling back to its HMAC-commitment scheme otherwise — ONE verification path either way.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

from packages.brain_link_pool.peer_trust_guard import verify_signature
from packages.graph_scale.injection_guard import detect as detect_injection

PROTOCOL = "brain-link/1"


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def generate_identity() -> tuple[str, str]:
    """-> (pubkey_hex, secret). ed25519 keypair when available; else the HMAC commitment scheme
    (pubkey = sha256(secret) prefix — the peer proves knowledge of the secret per message)."""
    try:
        from cryptography.hazmat.primitives import serialization as _ser
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(_ser.Encoding.Raw,
                                             _ser.PublicFormat.Raw).hex()
        sec = priv.private_bytes(_ser.Encoding.Raw, _ser.PrivateFormat.Raw,
                                 _ser.NoEncryption()).hex()
        return pub, sec
    except ImportError:
        import secrets as _secrets
        sec = _secrets.token_hex(16)
        return hashlib.sha256(sec.encode()).hexdigest()[:32], sec


def sign(secret: str, payload: dict) -> str:
    """Sign the canonical payload with the identity's secret (ed25519 private key hex, or the
    HMAC-commitment 'secret:mac' fallback matching peer_trust_guard._hmac_verify)."""
    msg = canonical(payload).encode("utf-8")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret)).sign(msg).hex()
    except (ImportError, ValueError):
        mac = _hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return f"{secret}:{mac}"


def verify(pubkey: str, payload: dict, signature: str) -> bool:
    return verify_signature(pubkey, canonical(payload), signature)


@dataclass
class Hello:
    ai_id: str
    pubkey: str
    manifest: dict[str, Any]            # {tier, organs[], graph_size, battery_scores{}}
    nonce: str
    ts: float
    sig: str = ""

    def payload(self) -> dict:
        return {"kind": "hello", "protocol": PROTOCOL, "ai_id": self.ai_id, "pubkey": self.pubkey,
                "manifest": self.manifest, "nonce": self.nonce, "ts": self.ts}


@dataclass
class Turn:
    speaker: str                        # ai_id
    utterance: str
    bones: list = field(default_factory=list)       # [[s, r, o], ...] grounding of every claim
    evidence: list = field(default_factory=list)    # source strings for the bones
    ts: float = 0.0
    sig: str = ""

    def payload(self) -> dict:
        return {"kind": "turn", "protocol": PROTOCOL, "speaker": self.speaker,
                "utterance": self.utterance, "bones": self.bones, "evidence": self.evidence,
                "ts": self.ts}

    def is_grounded_claim(self) -> bool:
        return bool(self.bones)


@dataclass
class FactOffer:
    offerer: str
    bones: list                         # the offered triples
    evidence: list                      # offerer's sources (peer-side provenance, NOT consensus)
    ts: float = 0.0
    sig: str = ""

    def payload(self) -> dict:
        return {"kind": "fact_offer", "protocol": PROTOCOL, "offerer": self.offerer,
                "bones": self.bones, "evidence": self.evidence, "ts": self.ts}


def make_hello(ai_id: str, pubkey: str, secret: str, manifest: dict) -> Hello:
    h = Hello(ai_id=ai_id, pubkey=pubkey, manifest=manifest,
              nonce=hashlib.sha256(f"{ai_id}{time.time_ns()}".encode()).hexdigest()[:16],
              ts=time.time())
    h.sig = sign(secret, h.payload())
    return h


def make_turn(speaker: str, secret: str, utterance: str, bones: list | None = None,
              evidence: list | None = None) -> Turn:
    t = Turn(speaker=speaker, utterance=utterance, bones=bones or [], evidence=evidence or [],
             ts=time.time())
    t.sig = sign(secret, t.payload())
    return t


def make_fact_offer(offerer: str, secret: str, bones: list, evidence: list) -> FactOffer:
    f = FactOffer(offerer=offerer, bones=bones, evidence=evidence, ts=time.time())
    f.sig = sign(secret, f.payload())
    return f


def scan_message_text(*texts: str) -> list[dict[str, str]]:
    """Injection scan over every textual field of an inbound message. Findings are LOG MATERIAL —
    the message is still data; the guard's job is to make sure it never becomes instructions."""
    findings: list[dict[str, str]] = []
    for t in texts:
        if t:
            findings.extend(detect_injection(str(t)))
    return findings
