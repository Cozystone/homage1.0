# -*- coding: utf-8 -*-
"""Adaptive load signal — request latency must not be hostage to background learning.

Owner (2026-07-11): the ultimate battery's ONLY remaining wall is speed (p50/p95), and it is
NOT the answer path — an isolated instance with learners off passed the speed gates (round 12:
p50 2357ms). Live is slow because the always-on learners (firehose ~2.7k sentences/s, relation
discovery, browse-spool drain) are CPU-bound Python loops that hold the GIL and starve the
single request worker.

The fix is NOT to slow learning — the owner's whole thesis is that scale (more learning) closes
the gap. It is to make the learners YIELD to a request IN FLIGHT and run FULL SPEED when idle.
A chat request marks itself busy; the learners check this and back off hard while it runs, then
resume. Learning throughput is preserved during idle time (the vast majority); request latency
is protected during the rare active window.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_inflight = 0
_last_request_at = 0.0
_COOLDOWN_S = 0.6   # keep yielding briefly after a request ends (the answer may still be assembling)

# BOOT GRACE: on a cold start the answer path lazy-loads the pack + TripleStore + Kiwi (A1's
# ~15s cost). If the learners start hammering the CPU at the same instant, warmup and the first
# request contend and A1 times out (measured 19.6s on a fresh, learner-loaded boot). So the
# learners STAY QUIET until warmup signals done (or the grace elapses) — cold-boot CPU goes to
# loading + first requests, then learning ramps up.
_boot_at = time.time()
_BOOT_GRACE_S = 30.0
_warmup_done = False


def mark_warmup_done() -> None:
    global _warmup_done
    _warmup_done = True


def boot_settling() -> bool:
    """True while the engine is still cold-loading — learners should stay quiet."""
    return (not _warmup_done) and (time.time() - _boot_at < _BOOT_GRACE_S)


def wait_for_boot(poll: float = 1.0) -> None:
    """Called once at a learner's entry: block until warmup is done (or the grace elapses)."""
    while boot_settling():
        time.sleep(poll)


_req_started_at = 0.0


def enter_request() -> None:
    global _inflight, _last_request_at, _req_started_at
    with _lock:
        _inflight += 1
        _last_request_at = time.time()
        _req_started_at = _last_request_at


def request_elapsed() -> float:
    """Seconds since the current request entered — 0 when idle. Lets the web funnel enforce a
    per-answer wall budget so a chain of retrieval calls can't run an answer to 30-60s (the
    'uniform 100%' enemy: an over-budget answer times out the caller and becomes a miss)."""
    with _lock:
        return (time.time() - _req_started_at) if _inflight > 0 and _req_started_at else 0.0


def exit_request() -> None:
    global _inflight, _last_request_at
    with _lock:
        _inflight = max(0, _inflight - 1)
        _last_request_at = time.time()


def busy() -> bool:
    """True while a request is in flight OR within the cool-down after one finished."""
    with _lock:
        return _inflight > 0 or (time.time() - _last_request_at) < _COOLDOWN_S


def yield_to_requests(idle: float = 0.03, under_load: float = 0.25) -> None:
    """A learner's GIL-yield point: a short breath when idle (keep learning fast), a long one
    while a request is being served (hand the GIL to the request worker)."""
    time.sleep(under_load if busy() else idle)


def lower_process_priority() -> str:
    """Self-demote THIS process to idle/lowest CPU priority so the OS scheduler hands cores to
 the answer engine first. The learners already run in their OWN process ( B), but without a
 priority gap the two processes compete equally for cores — measured ~1s of the answer latency
 (2026-07-13). A learner daemon calls this at startup: it keeps running full speed on idle
 cores, but yields the instant the engine needs the CPU. Cross-platform, never fatal."""
    try:
        import os
        if hasattr(os, "nice"):        # POSIX: nice 19 = lowest
            os.nice(19)
            return "nice(19)"
    except Exception:
        pass
    try:                                # Windows: IDLE_PRIORITY_CLASS via ctypes
        import ctypes
        IDLE_PRIORITY_CLASS = 0x00000040
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.kernel32.SetPriorityClass(h, IDLE_PRIORITY_CLASS):
            return "IDLE_PRIORITY_CLASS"
    except Exception:
        pass
    return "unchanged"
