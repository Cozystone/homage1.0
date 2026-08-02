# -*- coding: utf-8 -*-
"""Phone-Link relay — runs on OUR cloud VM (same engine image), never a third
party. A phone posts an utterance under a pairing code; the paired machine
pulls it. PRIVACY BY STRUCTURE: bounded in-memory queues only, audio is
DELETED on pull or after 120s, no transcription or storage happens here — the
relay cannot understand what it carries.

POST /api/link/{code}/utterance   {audio_b64}
GET  /api/link/{code}/pull        -> {audio_b64} | 204
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/link", tags=["phone-link-relay"])

_TTL_S = 120
_MAX_PER_CODE = 6
_MAX_CODES = 500
_queues: dict[str, deque[tuple[float, str]]] = {}
_lock = threading.Lock()


class UtteranceIn(BaseModel):
    audio_b64: str = Field(min_length=8, max_length=8_000_000)  # ~6MB audio cap


def _gc() -> None:
    now = time.time()
    dead: list[str] = []
    for code, q in _queues.items():
        while q and now - q[0][0] > _TTL_S:
            q.popleft()
        if not q:
            dead.append(code)
    for code in dead:
        del _queues[code]


@router.post("/{code}/utterance")
def push(code: str, body: UtteranceIn) -> dict[str, Any]:
    if not (6 <= len(code) <= 24) or not code.isalnum():
        raise HTTPException(status_code=400, detail="bad code")
    with _lock:
        _gc()
        if code not in _queues and len(_queues) >= _MAX_CODES:
            raise HTTPException(status_code=503, detail="relay full")
        q = _queues.setdefault(code, deque(maxlen=_MAX_PER_CODE))
        q.append((time.time(), body.audio_b64))
        return {"queued": len(q), "ttl_s": _TTL_S, "stored": False}


@router.get("/{code}/pull")
def pull(code: str) -> Any:
    with _lock:
        _gc()
        q = _queues.get(code.upper()) or _queues.get(code)
        if not q:
            return Response(status_code=204)
        _ts, audio = q.popleft()
        return {"audio_b64": audio}
