# -*- coding: utf-8 -*-
"""Operator dashboard — the owner's one-screen truth panel.

Owner (2026-07-11): " AI , 
 (, ) ." Read-only aggregation of what already exists:
battery verdict, learner intake, thinking stream, voice diet, wheel readiness. No new state, no
writes — a window, not a lever. The /ops page is a single static HTML the engine serves itself
(zero CORS), and the same file deploys to Vercel where the BROWSER still fetches the LOCAL
engine — telemetry never leaves the machine.
"""
from __future__ import annotations

import glob
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_ROOT = Path(__file__).resolve().parents[4]


def _read_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.get("/api/ops/overview")
def ops_overview() -> dict[str, Any]:
    out: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    # ── battery: latest run verdict ────────────────────────────────────────────
    try:
        runs = sorted(glob.glob(str(_ROOT / "data" / "answer_quality" / "ultimate_battery" / "run_*.json")))
        d = _read_json(Path(runs[-1])) if runs else {}
        lat = d.get("latency_ms") or {}
        out["battery"] = {
            "verdict": d.get("verdict"),
            "p0": d.get("p0_pass"), "p1": d.get("p1_pass"),
            "p0_rate": d.get("p0_rate"), "p1_rate": d.get("p1_rate"),
            "p2": d.get("p2_pass"), "p2_rate": d.get("p2_rate"),
            "p50_ms": lat.get("p50"), "p95_ms": lat.get("p95"),
            "cases": len(d.get("cases") or []), "run": Path(runs[-1]).name if runs else None,
        }
    except Exception:
        out["battery"] = {}
    # ── learner sidecar (process-isolated intake) ─────────────────────────────
    st = _read_json(_ROOT / "data" / "autonomy" / "learner_daemon_status.json")
    cont = st.get("continuous") or {}
    out["learner"] = {
        "sidecar_at": st.get("at"), "pid": st.get("pid"),
        "running": bool(cont.get("running")),
        "ticks": cont.get("ticks", 0), "sentences_fed": cont.get("sentences_fed", 0),
        "sentences_accepted": cont.get("sentences_accepted", 0),
        "concepts_added": cont.get("concepts_added", 0),
        "relations_added": cont.get("relations_added", 0),
        "last_titles": cont.get("last_titles") or [],
        "source": cont.get("source"), "last_error": cont.get("last_error"),
        "firehose_per_second": (st.get("firehose") or {}).get("per_second", 0),
        "firehose_unique": (st.get("firehose") or {}).get("unique", 0),
        "reldisc_checks": (st.get("relation_discovery") or {}).get("checks", 0),
        "reldisc_linked": (st.get("relation_discovery") or {}).get("linked", 0),
    }
    # ── P0 sentinel (unattended answer-quality guard) ────────────────────────
    sent = _read_json(_ROOT / "data" / "autonomy" / "p0_sentinel_status.json")
    out["sentinel"] = {
        "at": sent.get("at"), "state": sent.get("state"),
        "passed": sent.get("passed"), "total": sent.get("total"),
        "frozen": (_ROOT / "data" / "autonomy" / "LEARNING_FROZEN").exists(),
        "fails": [f.get("q") for f in (sent.get("fails") or [])],
    } if sent else {"state": "warming"}
    # ── voice diet ────────────────────────────────────────────────────────────
    try:
        from packages.autonomy_kernel.narrative_corpus import stats as _corpus_stats
        out["voice_diet"] = _corpus_stats()
    except Exception:
        out["voice_diet"] = {}
    # ── knowledge spool depth (browse → learn backlog) ────────────────────────
    try:
        sp = _ROOT / "data" / "autonomy" / "browse_candidates.jsonl"
        out["browse_spool_pages"] = len(sp.read_text(encoding="utf-8").splitlines()) if sp.exists() else 0
    except Exception:
        out["browse_spool_pages"] = 0
    # ── thinking stream (live ticker + voice + recent) ────────────────────────
    try:
        from packages.autonomy_kernel.activity_feed import feed
        f = feed(limit=14)
        out["thinking"] = {"ticker": f.get("ticker"), "voice": f.get("voice"),
                           "current_kind": f.get("current_kind"), "recent": f.get("recent") or []}
    except Exception:
        out["thinking"] = {}
    # ── flywheel / wheel readiness (cached numbers only — no retrain here) ────
    try:
        from packages.flywheel.logger import flywheel_stats
        out["flywheel"] = flywheel_stats()
    except Exception:
        out["flywheel"] = {}
    # ── failure-receipt steer: junk domains to avoid, knowledge gaps to seek ──
    try:
        from packages.flywheel.failure_receipts import receipt_stats, search_bias
        out["failure_receipts"] = {**receipt_stats(), "steer": search_bias()}
    except Exception:
        out["failure_receipts"] = {}

    try:
        sm = _ROOT / "data" / "answer_quality" / "story_metrics.jsonl"
        rows = [json.loads(x) for x in sm.read_text(encoding="utf-8").splitlines()[-8:] if x.strip()]
        if rows:
            out["story_fluency"] = {
                "last": rows[-1],
                "avg_ttr": round(sum(r.get("ttr", 0) for r in rows) / len(rows), 3),
                "avg_distinct2": round(sum(r.get("distinct2", 0) for r in rows) / len(rows), 3),
                "samples": len(rows),
            }
        else:
            out["story_fluency"] = {}
    except Exception:
        out["story_fluency"] = {}
    # ── felt (mood tail) ──────────────────────────────────────────────────────
    try:
        felt_p = _ROOT / "data" / "autonomy" / "felt.jsonl"
        rows = [json.loads(x) for x in felt_p.read_text(encoding="utf-8").splitlines()[-5:] if x.strip()]
        out["felt_tail"] = [{"at": r.get("at"), "valence": r.get("valence"),
                             "excerpt": str(r.get("excerpt") or "")[:40]} for r in rows]
    except Exception:
        out["felt_tail"] = []
    return out


_OPS_HTML_PATH = _ROOT / "apps" / "api" / "app" / "static" / "ops.html"


@router.get("/ops")
def ops_page() -> HTMLResponse:
    try:
        return HTMLResponse(_OPS_HTML_PATH.read_text(encoding="utf-8"))
    except Exception:
        return HTMLResponse("<h3>ops.html missing</h3>", status_code=500)
