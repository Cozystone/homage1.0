# -*- coding: utf-8 -*-
"""Rate limiting — DoS defense for the Brain Link pool (threat model §2).

Two distinct floods, two distinct defenses (they are not the same problem):

  * NEW-IDENTITY flood (Sybil register storm) — an attacker spins up endless
    fresh keys to exhaust the coordinator. Per-identity limiting can't help (each
    request IS a new identity), so the defense is (a) the registration PoW cost
    already in peer_trust_guard, plus (b) a GLOBAL registration ceiling here: the
    pool accepts at most N joins per window, whoever they are.

  * ESTABLISHED-PEER abuse (claim storm) — a real peer hammers /work/claim to
    hog batches or thrash the coordinator. The defense is a per-identity TOKEN
    BUCKET: steady sustainable rate with a burst allowance, so an honest peer's
    natural bursts pass while a runaway is throttled — fair, not punitive.

Token bucket (not a fixed window): tokens refill continuously at `rate`/sec up
to `burst`; each action costs one token. An idle peer banks up to `burst`, so a
legitimate flurry after a pause is fine; sustained abuse drains and is refused
with a retry-after. Deterministic, in-memory, thread-safe.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class TokenBucket:
    """Continuous-refill bucket: `rate` tokens/sec, capacity `burst`."""

    __slots__ = ("rate", "burst", "_tokens", "_ts", "_lock")

    def __init__(self, rate: float, burst: float) -> None:
        self.rate = float(rate)
        self.burst = float(burst)
        self._tokens = float(burst)
        self._ts = time.monotonic()
        self._lock = threading.Lock()

    def take(self, cost: float = 1.0) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self.burst, self._tokens + (now - self._ts) * self.rate)
            self._ts = now
            if self._tokens >= cost:
                self._tokens -= cost
                return {"allowed": True, "remaining": round(self._tokens, 2)}
            deficit = cost - self._tokens
            return {"allowed": False, "retry_after_s": round(deficit / self.rate, 2),
                    "remaining": round(self._tokens, 2)}


class PerIdentityLimiter:
    """One token bucket per identity, created on first use, LRU-evicted so a
    Sybil storm of keys can't grow the map without bound."""

    def __init__(self, rate: float, burst: float, *, max_keys: int = 10_000) -> None:
        self.rate, self.burst, self.max_keys = rate, burst, max_keys
        self._buckets: dict[str, TokenBucket] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def check(self, key: str, cost: float = 1.0) -> dict[str, Any]:
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                if len(self._buckets) >= self.max_keys:
                    old = self._order.popleft()
                    self._buckets.pop(old, None)
                b = TokenBucket(self.rate, self.burst)
                self._buckets[key] = b
                self._order.append(key)
        return b.take(cost)


class GlobalRateCeiling:
    """A single shared bucket for an action regardless of caller — the ceiling a
    Sybil register storm hits (no per-identity gaming possible)."""

    def __init__(self, rate: float, burst: float) -> None:
        self._bucket = TokenBucket(rate, burst)

    def check(self, cost: float = 1.0) -> dict[str, Any]:
        return self._bucket.take(cost)


# ── singletons for the Brain Link endpoints (tuned ABOVE measured honest use) ──
# registration: pool-wide 2/sec, burst 20 (a legit fleet joining is fine; a
# storm of thousands/sec is refused — combined with the PoW cost this is stiff).
_REGISTER_CEILING = GlobalRateCeiling(rate=2.0, burst=20.0)
# claim: per-peer 50/sec, burst 200 — deliberately ABOVE the fastest MEASURED
# honest peer (docker-peer-1 benched 800 sents/sec ≈ 32 claims/sec at batch 25).
# Only genuine thrashing (>50 claims/sec sustained) is throttled; real work is
# never touched, and this never affects reputation.
_CLAIM_LIMITER = PerIdentityLimiter(rate=50.0, burst=200.0)


def allow_registration() -> dict[str, Any]:
    """Global registration ceiling (Sybil-storm defense; pairs with PoW)."""
    return _REGISTER_CEILING.check()


def allow_claim(peer_id: str) -> dict[str, Any]:
    """Per-peer claim rate (established-peer abuse defense)."""
    return _CLAIM_LIMITER.check(str(peer_id or "anon"))
