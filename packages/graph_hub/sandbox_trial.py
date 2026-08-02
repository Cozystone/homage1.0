from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .audit import append_graph_hub_audit_event
from .cartridge_mount import (
    attach_cartridge_namespace,
    detach_cartridge_namespace,
    materialize_cartridge_chunk,
    select_cartridge_chunks,
)
from .cartridge_profile import SandboxTrialSession, to_dict
from .local_fingerprint import local_seed_fingerprint
from .models import GRAPH_HUB_ROOT, read_json, stable_id, utc_now_iso, write_json
from .synergy import score_cartridge_synergy


TRIALS_PATH = GRAPH_HUB_ROOT / "trials" / "sandbox_trials.json"
TRIAL_QUERY_LIMIT = 5
TRIAL_TTL_MINUTES = 30


def _load_trials() -> dict[str, dict[str, Any]]:
    payload = read_json(TRIALS_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save_trials(payload: dict[str, dict[str, Any]]) -> None:
    write_json(TRIALS_PATH, payload)


def _expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=TRIAL_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _overlay_id(session_id: str) -> str:
    return stable_id("wm_overlay", session_id)


def start_sandbox_trial(cartridge_id: str, *, intent: str | None = None) -> dict[str, Any]:
    synergy = score_cartridge_synergy(cartridge_id, active_context=intent)
    local_fingerprint_hash = str(local_seed_fingerprint().get("fingerprint_hash"))
    if not synergy.get("safe_to_trial"):
        session_id = stable_id("trial", f"{cartridge_id}:{utc_now_iso()}:failed")
        session = SandboxTrialSession(
            session_id=session_id,
            cartridge_id=cartridge_id,
            user_local_fingerprint_hash=local_fingerprint_hash,
            remaining_queries=0,
            attached_chunks=[],
            working_memory_overlay_id=_overlay_id(session_id),
            state="failed",
            local_write=False,
            cloud_merge=False,
            started_at=utc_now_iso(),
            expires_at=_expires_at(),
            query_results=[],
            cleanup_status="not_started",
        )
        return {**to_dict(session), "reason": "synergy_not_safe", "pair_edges_sent": 0}
    attach = attach_cartridge_namespace(cartridge_id)
    selected = select_cartridge_chunks(intent or cartridge_id, max_chunks=int(synergy.get("recommended_active_chunks") or 2))
    session_id = stable_id("trial", f"{cartridge_id}:{utc_now_iso()}:{synergy.get('local_fingerprint_hash')}")
    session = SandboxTrialSession(
        session_id=session_id,
        cartridge_id=cartridge_id,
        user_local_fingerprint_hash=local_fingerprint_hash,
        remaining_queries=TRIAL_QUERY_LIMIT,
        attached_chunks=list(selected.get("selected_chunks") or []),
        working_memory_overlay_id=_overlay_id(session_id),
        state="active" if attach.get("state") == "mounted" else "failed",
        local_write=False,
        cloud_merge=False,
        started_at=utc_now_iso(),
        expires_at=_expires_at(),
        query_results=[],
        cleanup_status="active",
    )
    trials = _load_trials()
    trials[session_id] = to_dict(session)
    _save_trials(trials)
    append_graph_hub_audit_event("sandbox_trial_started", cartridge_id, {"session_id": session_id, "remaining_queries": TRIAL_QUERY_LIMIT})
    return {**to_dict(session), "synergy": synergy, "pair_edges_sent": 0}


def get_sandbox_trial(session_id: str) -> dict[str, Any]:
    session = _load_trials().get(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    return session


def detach_sandbox_trial(session_id: str) -> dict[str, Any]:
    trials = _load_trials()
    session = trials.get(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    detach = detach_cartridge_namespace(str(session.get("cartridge_id") or ""))
    session = {
        **session,
        "state": "detached",
        "remaining_queries": 0,
        "attached_chunks": [],
        "cleanup_status": "working_memory_overlay_purged",
        "local_write": False,
        "cloud_merge": False,
        "local_fingerprint_unchanged": session.get("user_local_fingerprint_hash") == local_seed_fingerprint().get("fingerprint_hash"),
    }
    trials[session_id] = session
    _save_trials(trials)
    append_graph_hub_audit_event("sandbox_trial_detached", str(session.get("cartridge_id")), {"session_id": session_id, "cleanup_status": session["cleanup_status"]})
    return {**session, "detach": detach, "pair_edges_sent": 0}


def _graph_extract_answer(query: str, materialized: dict[str, Any]) -> str:
    nodes = materialized.get("nodes") or []
    edges = materialized.get("edges") or []
    labels = [str(node.get("label") or node.get("id")) for node in nodes[:4]]
    relations = [str(edge.get("relation") or "relates_to") for edge in edges[:3]]
    if labels and relations:
        return f"Sandbox graph evidence matched {', '.join(labels)} through {', '.join(relations)} relations for this query."
    if labels:
        return f"Sandbox graph evidence matched {', '.join(labels)} for this query."
    return "No bounded cartridge chunk produced evidence for this query."


def run_sandbox_trial_query(session_id: str, query: str) -> dict[str, Any]:
    start = time.perf_counter()
    trials = _load_trials()
    session = trials.get(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    if session.get("state") != "active" or int(session.get("remaining_queries") or 0) <= 0:
        return {**session, "state": session.get("state", "detached"), "answer": "", "remaining_queries": 0, "local_write": False, "cloud_merge": False, "pair_edges_sent": 0}
    selected = select_cartridge_chunks(query, max_chunks=2)
    chunks = list(selected.get("selected_chunks") or session.get("attached_chunks") or [])[:2]
    materialized = {"nodes": [], "edges": [], "materialized_nodes": 0, "materialized_edges": 0}
    if chunks:
        chunk = chunks[0]
        materialized = materialize_cartridge_chunk(str(chunk.get("cartridge_id")), str(chunk.get("chunk_id")), max_nodes=64, max_edges=128)
    remaining = max(0, int(session.get("remaining_queries") or 0) - 1)
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    result = {
        "query": query,
        "answer": _graph_extract_answer(query, materialized),
        "answer_mode": "bounded_graph_extract",
        "materialized_nodes": int(materialized.get("materialized_nodes") or 0),
        "materialized_edges": int(materialized.get("materialized_edges") or 0),
        "remaining_queries": remaining,
        "local_write": False,
        "cloud_merge": False,
        "temporary": True,
        "pair_edges_sent": 0,
        "latency_ms": latency_ms,
    }
    session = {
        **session,
        "remaining_queries": remaining,
        "attached_chunks": chunks,
        "query_results": list(session.get("query_results") or []) + [result],
        "local_write": False,
        "cloud_merge": False,
    }
    trials[session_id] = session
    _save_trials(trials)
    if remaining == 0:
        detached = detach_sandbox_trial(session_id)
        return {**result, "session_id": session_id, "state": "detached", "cleanup_status": detached["cleanup_status"]}
    append_graph_hub_audit_event("sandbox_trial_query", str(session.get("cartridge_id")), {"session_id": session_id, "remaining_queries": remaining, "latency_ms": latency_ms})
    return {**result, "session_id": session_id, "state": "active", "cleanup_status": "active"}
