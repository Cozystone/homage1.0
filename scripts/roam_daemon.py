# -*- coding: utf-8 -*-
"""Detached roaming daemon -- the curiosity loop that never stops exploring.

Cycle: pick pairs the field is UNSURE about (self-directed curiosity, plus any pairs queued by
exams/solvers in curiosity_queue.txt) -> hybrid browser roam (predict->surf->mine->consensus->
receipt) -> every N pairs, refit the phase field so roamed knowledge enters the cognitive space.
Anti-dogma: explored pairs get re-queued with age, so beliefs are revisited, never frozen.
Log: data/temporal_reasoning/roam_daemon.log
"""
import gc
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.temporal_reasoning.precedence_field import PrecedenceField          # noqa: E402
from packages.temporal_reasoning.browser_roamer import browser_roam_pair          # noqa: E402
from packages.temporal_reasoning.web_explorer import refit_with_web               # noqa: E402

DIR = ROOT / "data" / "temporal_reasoning"
LOG = DIR / "roam_daemon.log"
QUEUE = DIR / "curiosity_queue.txt"        # one "a b" per line; exams/solvers append here
REFIT_EVERY = 6
RSS_CAP_MB = 800                           # growth gate: browser roam leaked to 3.9GB over 13h;
                                           # cap RSS and self-restart clean so it can NEVER grow
                                           # unbounded again ([[engine-memory-killloop-fix]] pattern)


def _rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        return 0.0


def _growth_gate() -> None:
    """If RSS exceeds the cap, GC; if still over, RE-EXEC this daemon clean (reclaims any leaked
    browser/context memory). Ultra-low-power target: bounded footprint, always."""
    rss = _rss_mb()
    if rss < RSS_CAP_MB:
        return
    gc.collect()
    if _rss_mb() < RSS_CAP_MB:
        return
    log(f"growth-gate: RSS {rss:.0f}MB > {RSS_CAP_MB}MB -> self-restart (reclaim leaked memory)")
    os.execv(sys.executable, [sys.executable] + sys.argv)


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def curiosity_pairs(field: PrecedenceField, k: int = 4) -> list[tuple[str, str]]:
    """Self-directed targets: frequent tokens whose mutual order the field barely knows."""
    toks = sorted(field.seen, key=field.seen.get, reverse=True)[:400]
    rng = random.Random()
    out = []
    for _ in range(600):
        a, b = rng.sample(toks, 2)
        c = field.order_confidence(a, b)
        if c is not None and abs(c - 0.5) < 0.06:        # genuinely unsure -> curious
            out.append((a, b))
            if len(out) >= k:
                break
    return out


def queued_pairs() -> list[tuple[str, str]]:
    if not QUEUE.exists():
        return []
    pairs = []
    for ln in QUEUE.read_text(encoding="utf-8").splitlines():
        parts = ln.strip().split()
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    QUEUE.write_text("", encoding="utf-8")               # consumed
    return pairs


def main() -> None:
    log("roam daemon up")
    n = 0
    while True:
        field = PrecedenceField.load()
        targets = queued_pairs() + curiosity_pairs(field)
        if not targets:
            time.sleep(120)
            continue
        for a, b in targets:
            try:
                r = browser_roam_pair(a, b, field=field)
                v = r["verdict"]
                log(f"roam ({a},{b}): obs={r['observations']} pages={r['pages']} "
                    f"consensus={None if v is None else round(v[0], 3)}")
            except Exception as e:                        # network hiccups never kill curiosity
                log(f"roam ({a},{b}) error: {type(e).__name__}: {e}")
            n += 1
            if n % REFIT_EVERY == 0:
                try:
                    f2 = refit_with_web()
                    log(f"refit: {len(f2.phase)} tokens")
                except Exception as e:
                    log(f"refit error: {type(e).__name__}")
            gc.collect()                                 # release each roam's browser artifacts
            _growth_gate()                               # bounded RSS — self-restart if it leaks
            time.sleep(90)                                # pace: be a polite citizen of the web


if __name__ == "__main__":
    main()
