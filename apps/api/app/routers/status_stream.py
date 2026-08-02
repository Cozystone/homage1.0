"""Single SSE status channel ( P4 — the polling-storm replacement).

The dashboard used to poll ~30 status endpoints every few seconds, keeping the
browser and the API permanently busy. This router pushes ONE merged status
document over Server-Sent Events instead: the server composes the snapshot at
its own cadence and only emits when something actually changed (hash diff), so
an idle system costs one comparison per interval and zero bytes on the wire.

Frontend contract:
 const es = new EventSource(`${API_BASE}/api/status/stream`);
 es.onmessage = (e) => setStatus(JSON.parse(e.data)); // whole merged doc
Panels subscribe to slices of the one document. Migration is incremental —
REST endpoints stay; consumers move over one by one.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/status", tags=["status-stream"])

_INTERVAL_SEC = 2.0
_HEARTBEAT_SEC = 25.0  # keep proxies from closing an idle stream


# Learning-metric fields that advance every tick even when nothing meaningful for
# the UI changed — excluded from the change-hash so a truly idle system stays quiet,
# but still sent in the payload (they are cheap and the panels display them).
_VOLATILE_LEARNING_KEYS = ("uptime_seconds",)


def _snapshot() -> dict[str, Any]:
    """Compose the merged status document from in-process state (no self-HTTP).

    Returns the CONTENT only (no per-call timestamp); the stream adds `ts` at send
    time so the change-hash reflects real state changes, not the clock. `learning`
    carries the FULL continuous metrics so every panel that used to poll
    /learning/continuous/metrics can read this one slice instead.
    """
    doc: dict[str, Any] = {"engine": "up"}
    try:
        from .cloud_brain import cloud_brain_continuous_metrics

        doc["learning"] = dict(cloud_brain_continuous_metrics())
    except Exception as exc:  # a broken sub-status must not kill the stream
        doc["learning"] = {"error": str(exc)[:120]}
    try:
        from .base_brain import base_brain_status

        b = base_brain_status()
        doc["base_brain"] = {k: b.get(k) for k in ("ready", "concept_count", "pack_version") if k in b}
    except Exception as exc:
        doc["base_brain"] = {"error": str(exc)[:120]}
    return doc


def _change_key(doc: dict[str, Any]) -> str:
    """Hash of the meaningful content — excludes clock-like fields so an idle
    system does not emit every interval."""
    learning = dict(doc.get("learning") or {})
    for k in _VOLATILE_LEARNING_KEYS:
        learning.pop(k, None)
    stable = {**doc, "learning": learning}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


async def _event_stream() -> AsyncIterator[str]:
    last_hash = ""
    last_sent = 0.0
    while True:
        doc = await asyncio.to_thread(_snapshot)
        digest = _change_key(doc)
        now = time.time()
        if digest != last_hash:
            last_hash = digest
            last_sent = now
            doc["ts"] = now
            yield f"data: {json.dumps(doc, ensure_ascii=False)}\n\n"
        elif now - last_sent >= _HEARTBEAT_SEC:
            last_sent = now
            yield ": heartbeat\n\n"
        await asyncio.sleep(_INTERVAL_SEC)


@router.get("/stream")
async def status_stream() -> StreamingResponse:
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
