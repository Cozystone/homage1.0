# -*- coding: utf-8 -*-
"""ATANOR browser API — graph-native browsing ( P2/P2-2).

POST /api/browser/ingest {url, html?} -> distill + host-voiced record
GET /api/browser/promotable -> multi-host, judge-cleared candidates
GET /api/browser/stats

Fetches are safe-URL gated (public http(s), no private ranges); the verified
store is NEVER written from here — browsing observes, the promotion gate decides.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/browser", tags=["browser"])

_LEDGER = None


def _ledger():
    global _LEDGER
    if _LEDGER is None:
        from packages.atanor_browser.browser_ingest import BrowserEvidenceLedger

        _LEDGER = BrowserEvidenceLedger()
    return _LEDGER


def _fetch(url: str) -> str | None:
    """Bounded, safe-URL-gated fetch of a public page."""
    try:
        from packages.cloud_brain.web_seed_feeder import is_safe_public_url
    except Exception:
        is_safe_public_url = None
    if is_safe_public_url is not None:
        ok, _reason = is_safe_public_url(url)
        if not ok:
            return None
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "ATANOR-Browser/0.1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if int(resp.status) != 200:
                return None
            raw = resp.read(2_000_000)  # 2MB cap
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


@router.post("/ingest")
def browser_ingest(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    from packages.atanor_browser.browser_ingest import ingest_page

    url = str(body.get("url") or "")
    html = body.get("html")
    if not html:
        if not url:
            return {"ok": False, "reason": "url or html required"}
        html = _fetch(url)
        if html is None:
            return {"ok": False, "reason": "fetch blocked or failed (safe-URL gate)"}
    out = ingest_page(str(html), url=url, ledger=_ledger())
    return {"ok": True, **out}


@router.get("/promotable")
def browser_promotable() -> dict[str, Any]:
    store = None
    try:
        from packages.graph_scale.answer_bridge import _store

        store = _store()
    except Exception:
        store = None
    return {"promotable": _ledger().promotable(store=store)}


@router.get("/promote-preview")
def browser_promote_preview(auto_mode: bool = False) -> dict[str, Any]:
    """Run consensus-cleared candidates through the SAME default-deny promotion
    gate the rest of the engine uses — shows eligible vs blocked (+reasons).
    Writes nothing; the operator confirms actual promotion via the gate."""
    store = None
    try:
        from packages.graph_scale.answer_bridge import _store

        store = _store()
    except Exception:
        store = None
    return _ledger().gate_preview(store=store, auto_mode=auto_mode)


@router.post("/forget")
def browser_forget(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Inspect an erasure request without bypassing shipped-graph authority.

    This public route has no authenticated operator-signature channel, so it
    neither scans for the supplied subject nor mutates the graph. Actual
    erasure must flow through an immutable retraction batch and signed graph
    promotion.
    """
    subject = str(body.get("subject") or "").strip()
    if not subject:
        return {"ok": False, "reason": "subject required"}
    return {
        "ok": False,
        "accepted": False,
        "scanned": False,
        "applied": False,
        "reason": "authenticated_signed_graph_erasure_workflow_not_wired",
        "required_authority": "operator_signed_graph_mutation_batch",
    }


@router.get("/stats")
def browser_stats() -> dict[str, Any]:
    return _ledger().stats()


# ── personal activity journal (the AI browser's private brain graph) ──────────
@router.post("/activity")
def browser_activity(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Journal one browsing action into the PERSONAL brain graph (local only,
    PII-gated). This is the private lane — distinct from /ingest (shared)."""
    from packages.atanor_browser.activity_journal import record_activity

    return record_activity(
        kind=str(body.get("kind") or "visit"),
        url=str(body.get("url") or ""), query=str(body.get("query") or ""),
        title=str(body.get("title") or ""),
        dwell_s=float(body.get("dwell_s") or 0.0))


@router.get("/activity/recall")
def browser_activity_recall(q: str = "", limit: int = 20) -> dict[str, Any]:
    from packages.atanor_browser.activity_journal import recall

    return {"history": recall(query=q, limit=limit)}


@router.get("/activity/interests")
def browser_activity_interests() -> dict[str, Any]:
    from packages.atanor_browser.activity_journal import interests, revisits, sessions_summary

    return {"interests": interests(), "revisits": revisits(),
            "recent_sessions": sessions_summary()}


@router.get("/activity/status")
def browser_activity_status() -> dict[str, Any]:
    from packages.atanor_browser.activity_journal import status

    return status()


# ── session orchestration (the native shell drives these) ─────────────────────
_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        from packages.atanor_browser.browser_session import BrowserSession

        _SESSION = BrowserSession()
    return _SESSION


@router.post("/session/tab")
def browser_open_tab(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _session().open_tab(url=str(body.get("url") or ""))


@router.post("/session/navigate")
def browser_navigate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _session().navigate(
        str(body.get("tab_id") or ""), str(body.get("url") or ""),
        title=str(body.get("title") or ""),
        dom_text=body.get("html"),
        contribute_content=bool(body.get("contribute_content")))


@router.post("/session/close")
def browser_close_tab(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _session().close_tab(str(body.get("tab_id") or ""))


@router.get("/session/state")
def browser_session_state() -> dict[str, Any]:
    return _session().state()
