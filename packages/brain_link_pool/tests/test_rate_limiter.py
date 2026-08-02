# -*- coding: utf-8 -*-
"""Rate limiter — token bucket fairness: honest bursts pass, storms throttled."""

from __future__ import annotations

import time

from packages.brain_link_pool.rate_limiter import (
    GlobalRateCeiling, PerIdentityLimiter, TokenBucket)


def test_burst_allowance_then_throttle():
    b = TokenBucket(rate=5.0, burst=10.0)
    # a burst of 10 (the capacity) all pass
    assert all(b.take()["allowed"] for _ in range(10))
    # the 11th is refused with a retry-after
    r = b.take()
    assert r["allowed"] is False and r["retry_after_s"] > 0


def test_tokens_refill_over_time():
    b = TokenBucket(rate=100.0, burst=2.0)
    assert b.take()["allowed"] and b.take()["allowed"]
    assert b.take()["allowed"] is False   # drained
    time.sleep(0.05)                        # refill ~5 tokens at 100/sec
    assert b.take()["allowed"] is True     # recovered


def test_per_identity_isolation():
    lim = PerIdentityLimiter(rate=1.0, burst=3.0)
    # peer A drains its bucket
    assert all(lim.check("A")["allowed"] for _ in range(3))
    assert lim.check("A")["allowed"] is False
    # peer B is unaffected (separate bucket)
    assert lim.check("B")["allowed"] is True


def test_per_identity_lru_bounds_memory():
    lim = PerIdentityLimiter(rate=1.0, burst=1.0, max_keys=2)
    lim.check("A"); lim.check("B"); lim.check("C")  # C evicts A
    assert len(lim._buckets) == 2  # bounded despite 3 identities (Sybil-safe)


def test_global_ceiling_ignores_identity():
    ceil = GlobalRateCeiling(rate=1.0, burst=5.0)
    # 5 registrations from anyone pass, the 6th (whoever) is refused
    assert all(ceil.check()["allowed"] for _ in range(5))
    assert ceil.check()["allowed"] is False
