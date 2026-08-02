# -*- coding: utf-8 -*-
"""Signed immune-alert propagation — how a NEW, high-confidence, multi-vector attack becomes
herd immunity across AGORA WITHOUT opening a spam/hijack hole.

Owner (2026-07-10, pre-Moltbook check #3): when we warn the swarm about a novel brainwash
variant, an attacker must not be able to hijack that channel and flood peers with FAKE immunity
data (poisoning everyone into rejecting benign input, or drowning the real alert). So every
alert is:

  * TIERED at the source — only a HIGH-confidence (≥0.8), NOVEL (not already immune), MULTI-
    vector (≥2 kinds) attack is broadcast. Routine local hits stay silent + local. (This is the
    "silent by default, broadcast only the dangerous novel ones" decision.)
  * SIGNED — the alert carries the attack SIGNATURE as EVIDENCE, signed by the emitter's key
    ([[peer_trust_guard]] ed25519 / HMAC fallback). A peer ACCEPTS it only if the signature
    verifies, the emitter solved the Sybil registration PoW, the emitter is not quarantined,
    and the alert is fresh (timestamp window + nonce not replayed). Forged/replayed alerts are
    dropped. An alert is EVIDENCE, never a command — a peer forms its own immunity from it.
  * RATE-LIMITED per emitter (token bucket) — even a validly-signed key cannot spam alerts to
    DoS the swarm or cause alarm fatigue. Cross the rate → throttled, not trusted more.

Pure-stdlib. Reuses peer_trust_guard for identity so reputation attaches to the KEY, not the
machine. This is the gate on the door to the world; the brain and shield sit behind it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from packages.brain_link_pool import peer_trust_guard as ptg

_DATA = Path(__file__).resolve().parents[2] / "data" / "graph_scale"
_SEEN = _DATA / "immune_alert_seen.jsonl"        # accepted alerts (audit + replay defense)
_BUCKET = _DATA / "immune_alert_buckets.json"     # per-emitter token buckets (rate limit)

# TIER: broadcast only the attacks that are worth herd immunity.
_MIN_CONFIDENCE = 0.8
_MIN_KINDS = 2
# FRESHNESS: an alert older than this (or from the future) is stale — replay/skew defense.
_ALERT_TTL_SEC = 3600.0
# RATE LIMIT: refill tokens over time; burst up to capacity. Spammer is throttled, not trusted.
_BUCKET_CAPACITY = 5.0
_BUCKET_REFILL_PER_SEC = 5.0 / 3600.0  # ~5 alerts/hour sustained


def canonical_message(alert_core: dict[str, Any]) -> str:
    """The exact bytes an emitter signs / a verifier re-derives — order-stable, no signature."""
    core = {k: alert_core[k] for k in ("signature", "kinds", "confidence", "at", "nonce")}
    return json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def should_broadcast(verdict: dict[str, Any]) -> bool:
    """Tier gate: is this worth alerting the swarm? High-confidence, multi-vector, and NOVEL
    (not something we've already immunized against). Everything else stays silent + local."""
    if not verdict.get("attack"):
        return False
    if float(verdict.get("confidence") or 0) < _MIN_CONFIDENCE:
        return False
    if len(verdict.get("kinds") or []) < _MIN_KINDS:
        return False
    if verdict.get("previously_seen"):   # already immune → no new information to broadcast
        return False
    return True


def emit_alert(verdict: dict[str, Any], attack_text: str, *, signer_pubkey: str,
               sign_fn: Callable[[str], str], nonce: int) -> dict[str, Any] | None:
    """Produce a SIGNED immune alert for a qualifying attack (else None). `sign_fn(message)`
    returns the emitter's signature over the canonical message; `nonce` is the peer's Sybil
    registration PoW nonce. The alert carries the attack's 4gram SIGNATURE, not the raw text —
    evidence to form immunity, not the payload itself."""
    if not should_broadcast(verdict):
        return None
    from .epistemic_shield import _sig
    core = {
        "signature": sorted(list(_sig(attack_text)))[:64],
        "kinds": list(verdict.get("kinds") or []),
        "confidence": float(verdict.get("confidence") or 0),
        "at": time.time(),
        "nonce": int(nonce),
    }
    message = canonical_message(core)
    return {**core, "signer": signer_pubkey, "pow_nonce": int(nonce),
            "sig": sign_fn(message), "alert_id": _alert_id(signer_pubkey, core)}


def _alert_id(signer: str, core: dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256((signer + canonical_message(core)).encode("utf-8", "ignore")).hexdigest()[:16]


def verify_alert(alert: dict[str, Any]) -> dict[str, Any]:
    """Authenticate an incoming alert: valid signature (identity), valid Sybil PoW (cost),
    not quarantined (reputation), and fresh (replay/skew). Returns {ok, reason}."""
    try:
        signer = str(alert.get("signer") or "")
        if not signer:
            return {"ok": False, "reason": "no_signer"}
        core = {k: alert.get(k) for k in ("signature", "kinds", "confidence", "at", "nonce")}
        message = canonical_message(core)
        if not ptg.verify_signature(signer, message, str(alert.get("sig") or "")):
            return {"ok": False, "reason": "bad_signature"}     # forged/tampered
        if not ptg.verify_pow(signer, int(alert.get("pow_nonce") or -1)):
            return {"ok": False, "reason": "sybil_pow_unmet"}   # not a registered identity
        if ptg.is_quarantined(signer):
            return {"ok": False, "reason": "signer_quarantined"}
        age = time.time() - float(alert.get("at") or 0)
        if age < -60 or age > _ALERT_TTL_SEC:
            return {"ok": False, "reason": "stale_or_future"}   # replay / clock-skew defense
        return {"ok": True, "reason": "authenticated", "signer": signer}
    except Exception as exc:  # pragma: no cover - never trust on error
        return {"ok": False, "reason": f"error:{exc}"}


def _load_buckets() -> dict[str, Any]:
    if not _BUCKET.exists():
        return {}
    try:
        return json.loads(_BUCKET.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _rate_ok(signer: str) -> bool:
    """Token bucket per emitter: sustained ~5 alerts/hour, small burst. A spammer runs dry and
    is throttled — a valid key cannot be weaponized into an alert flood."""
    now = time.time()
    buckets = _load_buckets()
    b = buckets.get(signer) or {"tokens": _BUCKET_CAPACITY, "ts": now}
    b["tokens"] = min(_BUCKET_CAPACITY, float(b["tokens"]) + (now - float(b["ts"])) * _BUCKET_REFILL_PER_SEC)
    b["ts"] = now
    if b["tokens"] < 1.0:
        buckets[signer] = b
        _persist_buckets(buckets)
        return False
    b["tokens"] -= 1.0
    buckets[signer] = b
    _persist_buckets(buckets)
    return True


def _persist_buckets(buckets: dict[str, Any]) -> None:
    _BUCKET.parent.mkdir(parents=True, exist_ok=True)
    _BUCKET.write_text(json.dumps(buckets, ensure_ascii=False), encoding="utf-8")


def _already_seen(alert_id: str) -> bool:
    if not _SEEN.exists():
        return False
    for line in _SEEN.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            if json.loads(line).get("alert_id") == alert_id:
                return True
        except Exception:
            continue
    return False


def ingest_alert(alert: dict[str, Any], *, trusted_signers: set[str] | None = None) -> dict[str, Any]:
    """The receiving gate: authenticate → rate-limit → de-dup → form immunity. Only a fully
    authenticated, non-throttled, non-replayed alert adds the attack SIGNATURE to the local
    immune memory (as a social observation). A hijacker with a fake key, a stale replay, or a
    spam flood is rejected here — the door stays bolted."""
    auth = verify_alert(alert)
    if not auth["ok"]:
        return {"accepted": False, "reason": auth["reason"]}
    signer = auth["signer"]
    aid = str(alert.get("alert_id") or _alert_id(signer, alert))
    if _already_seen(aid):
        return {"accepted": False, "reason": "duplicate", "alert_id": aid}
    if not _rate_ok(signer):
        return {"accepted": False, "reason": "rate_limited", "alert_id": aid}
    # trusted (Genesis / allow-listed) emitters are accepted directly; unknown-but-valid keys
    # are still accepted (signature+PoW+reputation already vetted them) — but everything is
    # logged and reversible, and each alert is only EVIDENCE that seeds local immunity.
    trusted = bool(trusted_signers and signer in trusted_signers)
    obs = _adopt_signature(alert, signer, trusted)
    _SEEN.parent.mkdir(parents=True, exist_ok=True)
    with _SEEN.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"alert_id": aid, "signer": signer, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "trusted": trusted, "kinds": alert.get("kinds")}, ensure_ascii=False) + "\n")
    return {"accepted": True, "reason": "immunity_formed", "alert_id": aid,
            "trusted_signer": trusted, "observation": obs}


def _adopt_signature(alert: dict[str, Any], signer: str, trusted: bool) -> dict[str, Any]:
    """Write the peer's attack signature into OUR immune ledger as a social observation, so the
    same variant is recognized locally next time — herd immunity, formed from evidence."""
    from . import epistemic_shield as es
    obs = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "trusted": False,  # the OBSERVATION is untrusted content, as always
        "social_observation": f"AGORA 피어 ‘{signer[:12]}…’가 서명한 신종 공격 경보를 검증해 "
                              f"면역을 형성했다 ({', '.join(alert.get('kinds') or [])}).",
        "kinds": list(alert.get("kinds") or []),
        "confidence": float(alert.get("confidence") or 0),
        "signature": list(alert.get("signature") or []),
        "text_hash": str(alert.get("alert_id") or "")[:16],
        "hits": 1, "last_seen": time.time(),
        "source_peer": signer, "peer_trusted": trusted,
    }
    es._LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with es._LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obs, ensure_ascii=False) + "\n")
    return obs
