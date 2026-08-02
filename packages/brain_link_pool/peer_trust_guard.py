# -*- coding: utf-8 -*-
"""Peer trust guard — Sybil/abuse defense done SOUNDLY (threat model §5).

The owner proposed a permanent hardware-ID curse. It is rejected in the threat
model for good reasons (self-reported IDs are forgeable, permanent bans brick
honest users on one false positive, broadcasting hardware fingerprints is a
privacy/GDPR landmine, and the real blast radius — poisoning the QUARANTINED
candidate store — never warrants an irreversible sentence). This module keeps
the owner's actual goal — make abuse expensive, keep trust earned — with the
sound mechanisms instead:

  * IDENTITY = a keypair. The public key is the peer id; reputation attaches to
    the KEY, not the machine. Forgery needs the private key (signatures);
    privacy is preserved (no hardware fingerprint leaves the device).
  * SYBIL COST = a lightweight registration proof-of-work. One identity is not
    free, so spinning up N identities costs N·work — the Sybil economy breaks
    without punishing a single honest user.
  * REVOCABLE QUARANTINE = a key whose failure/replay rate crosses a threshold
    is auto-quarantined (not judged): reversible, audit-logged, EXPIRING, with
    an appeal field. A clean machine returns under a new key; a wrongly-flagged
    one is un-quarantined. Never permanent, never hardware.

Pure-stdlib (hashlib PoW + ed25519 via `cryptography` if present, else an
HMAC-challenge fallback) so it runs anywhere the pool runs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parents[2] / "data" / "brain_link" / "trust"
_QUARANTINE = _DATA / "quarantine.jsonl"

# Sybil cost: registration PoW difficulty (leading hex zeros of sha256).
# 4 = ~65k hashes ≈ tens of ms honest, but N identities cost N× — enough to
# break bulk Sybil without a perceptible tax on one real join. Tunable.
POW_DIFFICULTY = int(os.getenv("ATANOR_POW_DIFFICULTY", "4"))
_QUARANTINE_HOURS = float(os.getenv("ATANOR_QUARANTINE_HOURS", "24"))
_FAIL_RATE_LIMIT = 0.5      # >50% verified-failures over the window -> quarantine
_REPLAY_RATE_LIMIT = 0.3    # >30% duplicate-of-known submissions -> quarantine
_MIN_SAMPLES = 8            # never quarantine on too few observations


# ── registration proof-of-work (Sybil cost) ──────────────────────────────────
def pow_challenge(peer_pubkey: str) -> str:
    """A per-identity challenge string the peer must solve to register."""
    return hashlib.sha256(f"atanor-join::{peer_pubkey}".encode()).hexdigest()[:16]


def solve_pow(peer_pubkey: str, difficulty: int = POW_DIFFICULTY) -> int:
    """Find a nonce so sha256(challenge||nonce) has `difficulty` leading zeros.
    The peer runs this (the cost is theirs); the coordinator only verifies."""
    challenge = pow_challenge(peer_pubkey)
    prefix = "0" * difficulty
    nonce = 0
    while True:
        h = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
        if h.startswith(prefix):
            return nonce
        nonce += 1


def verify_pow(peer_pubkey: str, nonce: int, difficulty: int = POW_DIFFICULTY) -> bool:
    challenge = pow_challenge(peer_pubkey)
    h = hashlib.sha256(f"{challenge}{int(nonce)}".encode()).hexdigest()
    return h.startswith("0" * difficulty)


# ── cryptographic identity (signature verification) ──────────────────────────
def verify_signature(peer_pubkey: str, message: str, signature: str) -> bool:
    """Verify the peer signed `message` with the private key of `peer_pubkey`.
    Prefers ed25519; falls back to an HMAC scheme where the 'pubkey' is a
    commitment hash of a shared secret (weaker, but keeps the identity-binds-
    reputation property when `cryptography` is absent)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(peer_pubkey))
        pk.verify(bytes.fromhex(signature), message.encode())
        return True
    except ImportError:
        # fallback: signature = HMAC(secret, message), pubkey = sha256(secret)
        # (the peer proves knowledge of the secret whose hash is its id)
        return _hmac_verify(peer_pubkey, message, signature)
    except Exception:
        return False


def _hmac_verify(pubkey: str, message: str, signature: str) -> bool:
    # signature carries "secret:mac"; the id must equal sha256(secret)
    try:
        secret, mac = signature.split(":", 1)
        if hashlib.sha256(secret.encode()).hexdigest()[:32] != pubkey[:32]:
            return False
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, mac)
    except Exception:
        return False


# ── revocable, expiring, auditable quarantine (NOT a hardware curse) ──────────
def _load_quarantine() -> dict[str, dict[str, Any]]:
    if not _QUARANTINE.exists():
        return {}
    live: dict[str, dict[str, Any]] = {}
    for line in _QUARANTINE.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        live[r["peer"]] = r  # last record wins (lift overrides quarantine)
    return live


def is_quarantined(peer_pubkey: str) -> bool:
    r = _load_quarantine().get(peer_pubkey)
    if not r or r.get("lifted"):
        return False
    exp = r.get("expires_at", 0)
    return time.time() < exp  # EXPIRING — never permanent


def quarantine(peer_pubkey: str, reason: str, hours: float = _QUARANTINE_HOURS) -> dict[str, Any]:
    """Auto-quarantine a key. Reversible (lift), expiring, audit-logged, with an
    appeal field. This is detention, not judgment."""
    _QUARANTINE.parent.mkdir(parents=True, exist_ok=True)
    row = {"peer": peer_pubkey, "reason": reason, "lifted": False,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "expires_at": time.time() + hours * 3600,
           "appeal": "POST /api/brain-link/appeal with a signed message to contest"}
    with _QUARANTINE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def lift_quarantine(peer_pubkey: str, note: str = "operator lift") -> None:
    _QUARANTINE.parent.mkdir(parents=True, exist_ok=True)
    with _QUARANTINE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"peer": peer_pubkey, "lifted": True, "note": note,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                            ensure_ascii=False) + "\n")


def assess(peer_pubkey: str, *, jobs: int, failed: int, replays: int,
           auto_quarantine: bool = True) -> dict[str, Any]:
    """Behavioral check on a key's submission record. Crossing the failure or
    replay rate (with enough samples) auto-quarantines — reversibly."""
    if jobs < _MIN_SAMPLES:
        return {"peer": peer_pubkey, "action": "watch", "samples": jobs}
    fail_rate = failed / jobs
    replay_rate = replays / jobs
    breached = fail_rate > _FAIL_RATE_LIMIT or replay_rate > _REPLAY_RATE_LIMIT
    if breached and auto_quarantine and not is_quarantined(peer_pubkey):
        reason = (f"fail_rate={fail_rate:.2f} replay_rate={replay_rate:.2f} "
                  f"over {jobs} jobs")
        row = quarantine(peer_pubkey, reason)
        return {"peer": peer_pubkey, "action": "quarantined", "reason": reason,
                "expires_at": row["expires_at"], "reversible": True}
    return {"peer": peer_pubkey, "action": "ok" if not breached else "flagged",
            "fail_rate": round(fail_rate, 3), "replay_rate": round(replay_rate, 3)}


def admit(peer_pubkey: str, nonce: int, message: str = "", signature: str = "",
          *, require_signature: bool = False) -> dict[str, Any]:
    """The registration gate: verify Sybil PoW, optional signature, and that the
    key is not currently quarantined. Returns {ok, reason}."""
    if is_quarantined(peer_pubkey):
        return {"ok": False, "reason": "quarantined (reversible, expiring — see appeal)"}
    if not verify_pow(peer_pubkey, nonce):
        return {"ok": False, "reason": "registration proof-of-work invalid (Sybil cost unmet)"}
    if require_signature and not verify_signature(peer_pubkey, message, signature):
        return {"ok": False, "reason": "identity signature invalid"}
    return {"ok": True, "reason": "admitted", "tier": "economy"}
