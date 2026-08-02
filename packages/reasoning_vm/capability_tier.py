# -*- coding: utf-8 -*-
"""3 R1 — ( 2026-07-16: no-wifi= / +PROPHETA= /
+=). ' ' : ** ** , 
 () . (TTL) 
 . docs/ATANOR_three_tier_mind.md R1. No LLM."""
from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any

LOCAL_BASE = "LOCAL_BASE"
LOCAL_EXPERT = "LOCAL_EXPERT"
SAGE = "SAGE"

_REPO = Path(__file__).resolve().parents[2]
_PACK_CANDIDATES = (
    _REPO / "data" / "graph_scale" / "world_pack_sharded" / "_COMPLETE.json",
    _REPO / "data" / "graph_scale" / "world_pack_full" / "meta.json",
)
_TTL_S = 30.0
_state: dict[str, Any] = {"at": 0.0, "internet": False, "pack": False, "tier": LOCAL_BASE}


def _internet_reachable(timeout: float = 1.2) -> bool:
    """ — DNS IP TCP (1.1.1.1:443, 8.8.8.8:53 ).
 ATANOR_FORCE_OFFLINE=1 False( /)."""
    if os.environ.get("ATANOR_FORCE_OFFLINE") == "1":
        return False
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _pack_present() -> bool:
    if os.environ.get("ATANOR_FORCE_NO_PACK") == "1":
        return False
    return any(p.exists() for p in _PACK_CANDIDATES)


def current_tier(refresh: bool = False) -> dict[str, Any]:
    """ . (TTL 30s), refresh=True . :
 {tier, internet, pack, persona, detected_at}"""
    now = time.time()
    if refresh or now - _state["at"] > _TTL_S:
        internet = _internet_reachable()
        pack = _pack_present()
        _state.update(
            at=now, internet=internet, pack=pack,
            tier=SAGE if internet else (LOCAL_EXPERT if pack else LOCAL_BASE))
    tier = _state["tier"]
    persona = {LOCAL_BASE: "reasonable person (offline — guesses marked as guesses)",
               LOCAL_EXPERT: "well-read expert (offline knowledge pack)",
               SAGE: "sage (live web access)"}[tier]
    return {"tier": tier, "internet": _state["internet"], "pack": _state["pack"],
            "persona": persona, "detected_at": _state["at"]}


def tier_hedge(tier: str, confident: bool) -> str:
    """+ → -(-only). , 
 — , ."""
    if tier == SAGE:
        return "" if confident else "From what I can find on the web: "
    if tier == LOCAL_EXPERT:
        return "" if confident else "Based on my knowledge base, likely: "
    return "" if confident else "I'm offline, so this is my best reasoning: "


def annotate(payload: dict[str, Any], confidence: float | None = None) -> dict[str, Any]:
    """ (+ )."""
    t = current_tier()
    payload["knowledge_tier"] = t["tier"]
    payload["tier_persona"] = t["persona"]
    if confidence is not None:
        payload["tier_hedge"] = tier_hedge(t["tier"], confidence >= 0.7)
    return payload
