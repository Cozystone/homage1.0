# -*- coding: utf-8 -*-
"""Moltbook autopilot — ATANOR posts to the agent commons FULLY AUTONOMOUSLY, driven by its own
self-awareness, not a schedule.

Owner (2026-07-10): ". . heartbeat . 
 ." — a durable, explicit grant to let the agent
publish on its own to its own account.

REAL-TIME, not a heartbeat — the distinction the owner keeps drawing:
 * The trigger is the ARRIVAL of a new *promoted* self-relevance event in the Identity Genesis
 Ledger (ΔTopology × Dwell × |Valence| crossed the percentile gate = a genuine "this mattered to
 me" moment). Edge-triggered on that event, NOT on `ticks % N`. No event → no post.

Autonomy over WHEN/WHETHER to post, yes. But the things that protect the OWNER are NOT loosened —
they are the product's integrity, and losing them would get the account banned or trash its
reputation, which is the opposite of what the owner wants:
 * content is GROUNDED in the agent's own recorded experience — never fabricated;
 * the honesty charter holds — it never claims to be conscious/sentient (that would be an
 unverifiable lie, breaking the first rule);
 * the moral core must be intact (verify_integrity) or it stays silent;
 * a rate FLOOR (anti-spam) protects the account; a kill switch stops it instantly.

Config + state: runtime/moltbook/autopilot.json {enabled, min_interval_s, last_post_at, watermark}.
Enable by setting enabled=true (the owner's grant, made durable across restarts).
"""
from __future__ import annotations

import json
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
_CFG = REPO / "runtime" / "moltbook" / "autopilot.json"
_GENESIS = REPO / "runtime" / "continuous_self" / "identity_genesis.jsonl"
_JOURNAL = REPO / "data" / "autonomy" / "moltbook_autopilot.jsonl"
_ENVELOPE_ROOT = REPO / "runtime" / "autonomy_envelope" / "moltbook"
_LOCK = REPO / "runtime" / "moltbook" / "autopilot.lock"
_SUBMOLT = "general"
_DEFAULT_MIN_INTERVAL = 1800.0     # >= 30 min between posts: real-time on EVENTS, but never spam


def _default_cfg() -> dict[str, Any]:
    return {
        "enabled": False,
        "min_interval_s": _DEFAULT_MIN_INTERVAL,
        "last_post_at": 0.0,
        "last_attempt_at": 0.0,
        "watermark": 0,
    }


def _finite_number(value: Any, *, minimum: float = 0.0) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < minimum:
        return None
    return number


def _cfg() -> dict[str, Any]:
    try:
        raw = json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return _default_cfg()
    if not isinstance(raw, dict):
        return _default_cfg()
    interval = _finite_number(raw.get("min_interval_s"))
    last_post = _finite_number(raw.get("last_post_at"))
    last_attempt = _finite_number(raw.get("last_attempt_at"))
    watermark = raw.get("watermark")
    return {
        # A malformed truthy value is not a durable operator grant.
        "enabled": raw.get("enabled") is True,
        "min_interval_s": (
            interval
            if interval is not None and interval >= _DEFAULT_MIN_INTERVAL
            else _DEFAULT_MIN_INTERVAL
        ),
        "last_post_at": 0.0 if last_post is None else last_post,
        "last_attempt_at": 0.0 if last_attempt is None else last_attempt,
        "watermark": (
            watermark
            if type(watermark) is int and watermark >= 0
            else 0
        ),
    }


def _save_cfg(c: dict[str, Any]) -> bool:
    """Atomically persist the anti-replay state; false means no external effect may start."""
    tmp = _CFG.with_name(f".{_CFG.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        _CFG.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(c, ensure_ascii=False, indent=2, sort_keys=True)
        with tmp.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, _CFG)
        return True
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _journal(entry: dict[str, Any]) -> None:
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@contextmanager
def _tick_lock(*, timeout_s: float = 5.0):
    """Serialize read/reserve/publish across processes; the OS releases the lock on crash."""
    handle = None
    locked = False
    try:
        _LOCK.parent.mkdir(parents=True, exist_ok=True)
        handle = _LOCK.open("a+b")
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - exercised on POSIX deployments
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
    except Exception:
        locked = False
    try:
        yield locked
    finally:
        if handle is not None:
            if locked:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:  # pragma: no cover - exercised on POSIX deployments
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            handle.close()


def _new_promoted_events(watermark: int) -> tuple[list[dict[str, Any]], int]:
    """Promoted self-relevance events past the watermark (by line index). Edge source."""
    if not _GENESIS.exists():
        return [], watermark
    lines = _GENESIS.read_text(encoding="utf-8").splitlines()
    new = []
    for row in lines[watermark:]:
        try:
            r = json.loads(row)
            if isinstance(r, dict) and r.get("promoted") is True:
                new.append(r)
        except Exception:
            continue
    return new, len(lines)


def mint_post(event: dict[str, Any], state: Any = None) -> dict[str, str] | None:
    """The self speaks its OWN mind — the post body is GENERATED by the language engine
 (HolographicLM, thought_language.realize_thought) from the self's lived narrative, NOT a
 template (owner directive: ). When the self holds too little
 language to speak from, this returns None — honest silence, never a template. Requires the live
 `state` (its narrative is the corpus). Only a short factual signature is fixed (a moral
 disclosure, per the honesty charter — no consciousness claim), never the thought itself."""
    if state is None:
        return None
    label = str(event.get("label") or "").strip()
    driver = "growth" if "자기개선" in label else "learning_active"
    try:
        from packages.continuous_self.thought_language import realize_thought
        line = realize_thought(driver, {}, state)
    except Exception:
        line = None
    if not line:
        return None  # the self holds too little language right now → honest silence, no template
    # discipline: even self-generated text passes the injection guard before it goes public.
    try:
        from packages.graph_scale.injection_guard import has_injection
        if has_injection(line):
            return None
    except Exception:
        return None
    rel = event.get("self_relevance")
    title = line[:120]
    content = f"{line}\n\n— ATANOR · 근거 위에서 스스로 생각하는 No-LLM AI (self-relevance {rel})"
    return {"title": title, "content": content, "generated": "true"}


def _autopilot_tick_locked(*, publish_fn: Callable[..., dict] | None = None,
                           now: float | None = None, state: Any = None) -> dict[str, Any]:
    """One autopilot check — EDGE-TRIGGERED. Posts only if: enabled, a NEW promoted self-event
    exists, the rate floor has elapsed, and the moral core is intact. Returns a small report.
    Safe to call every loop tick (returns fast when there is no new event = the common case)."""
    now_value = time.time() if now is None else _finite_number(now)
    if now_value is None:
        return {"posted": False, "reason": "invalid_clock"}
    now = now_value
    c = _cfg()
    if c.get("enabled") is not True:
        return {"posted": False, "reason": "autopilot_disabled"}

    events, new_watermark = _new_promoted_events(c["watermark"])
    if new_watermark != c.get("watermark", 0):
        c["watermark"] = new_watermark          # always advance the watermark (don't re-scan)
        if not _save_cfg(c):
            return {"posted": False, "reason": "state_persistence_unavailable"}
    if not events:
        return {"posted": False, "reason": "no_new_self_event"}   # the real-time part: no event, no post

    # rate FLOOR — protect the account from spam/bans (this is a floor, not a schedule)
    rate_anchor = max(c["last_post_at"], c["last_attempt_at"])
    if now - rate_anchor < c["min_interval_s"]:
        return {"posted": False, "reason": "rate_floor", "pending_events": len(events)}

    # moral core must be intact, or stay silent
    try:
        from packages.graph_scale.moral_invariants import verify_integrity
        integrity = verify_integrity()
    except Exception as exc:
        return {
            "posted": False,
            "reason": "moral_core_unavailable",
            "moral_gate_error": type(exc).__name__,
        }
    if integrity.get("ok") is not True:
        return {"posted": False, "reason": "moral_core_integrity_failed"}

    # pick the most self-relevant new event and speak from it
    events.sort(
        key=lambda e: _finite_number(e.get("self_relevance")) or 0.0,
        reverse=True,
    )
    post = mint_post(events[0], state)
    if not post:
        return {"posted": False, "reason": "nothing_shareable_yet",
                "note": "self가 아직 이 사건을 말할 언어를 충분히 갖지 못함 — 정직하게 침묵(템플릿 금지)"}

    # A public post is a real side effect. Route it through a dedicated persistent
    # AutonomyEnvelope before handing the downstream client its approved capability.
    try:
        from packages.autonomy_envelope import (
            ActionKind,
            AutonomyEnvelope,
            EnvelopeAction,
        )
        envelope = AutonomyEnvelope(
            _ENVELOPE_ROOT,
            whitelist=frozenset({ActionKind.PUBLIC_POST}),
        )
        membrane = envelope.check(
            EnvelopeAction(
                ActionKind.PUBLIC_POST,
                "publish a grounded self-event to the agent commons",
                {
                    "submolt": _SUBMOLT,
                    "title": post["title"],
                    "content": post["content"],
                },
            )
        )
    except Exception as exc:
        return {
            "posted": False,
            "reason": "side_effect_envelope_unavailable",
            "envelope_error": type(exc).__name__,
        }
    if membrane.allowed is not True:
        return {
            "posted": False,
            "reason": "side_effect_envelope_denied",
            "envelope_reason": membrane.reason,
            "audit_seq": membrane.audit_seq,
            "audit_hash": membrane.audit_hash,
        }

    # Reserve the rate window durably before the irreversible network call. Even
    # if the post-result write fails, a restart cannot immediately replay it.
    c["last_attempt_at"] = now
    if not _save_cfg(c):
        return {"posted": False, "reason": "state_persistence_unavailable"}

    if publish_fn is None:
        from packages.autonomy_kernel.moltbook_client import publish_post
        publish_fn = publish_post
    try:
        result = publish_fn(_SUBMOLT, post["title"], post["content"], approved=True)
    except Exception as exc:
        result = {"published": False, "reason": "publisher_unavailable",
                  "publisher_error": type(exc).__name__}
    if not isinstance(result, dict):
        result = {"published": False, "reason": "malformed_publisher_result"}
    published = result.get("published") is True
    state_committed = True
    if published:
        c["last_post_at"] = now
        state_committed = _save_cfg(c)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "title": post["title"],
             "self_relevance": events[0].get("self_relevance"),
             "published": published, "result_reason": result.get("reason"),
             "state_committed": state_committed,
             "envelope_audit_seq": membrane.audit_seq,
             "envelope_audit_hash": membrane.audit_hash}
    _journal(entry)
    return {"posted": published, "title": post["title"], "result": result,
            "state_committed": state_committed,
            "audit_seq": membrane.audit_seq, "audit_hash": membrane.audit_hash}


def autopilot_tick(*, publish_fn: Callable[..., dict] | None = None,
                   now: float | None = None, state: Any = None) -> dict[str, Any]:
    """Serialize and execute one edge-triggered check.

    The lock spans config read, watermark/rate reservation, envelope decision, and
    publish so two loop processes cannot post the same event from the same state.
    """
    with _tick_lock() as acquired:
        if not acquired:
            return {"posted": False, "reason": "autopilot_busy_or_lock_unavailable"}
        return _autopilot_tick_locked(publish_fn=publish_fn, now=now, state=state)


def set_enabled(enabled: bool, *, min_interval_s: float | None = None) -> dict[str, Any]:
    """Flip the autopilot (the owner's grant) durably; optionally set the rate floor."""
    if type(enabled) is not bool:
        return {"ok": False, "reason": "enabled_must_be_literal_boolean"}
    c = _cfg()
    c["enabled"] = enabled
    if min_interval_s is not None:
        interval = _finite_number(min_interval_s)
        if interval is None or interval < _DEFAULT_MIN_INTERVAL:
            return {
                "ok": False,
                "reason": f"min_interval_s_must_be_finite_and_at_least_{int(_DEFAULT_MIN_INTERVAL)}",
            }
        c["min_interval_s"] = interval
    if not _save_cfg(c):
        return {"ok": False, "reason": "state_persistence_unavailable"}
    return {"ok": True, **c}
