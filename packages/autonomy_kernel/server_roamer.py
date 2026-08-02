# -*- coding: utf-8 -*-
"""Server-side roamer — the system VISITS the world by itself, no browser required.

Honest gap this closes (measured 2026-07-14): browse_director's field trips were only executed
when the Surfer extension had a browser open — grep showed next_destination consumed by tests and
the extension route alone. The owner's directive is ; so the
always-on autonomy loop needs its OWN legs. One roam tick:

 1. pick a destination — browse_director's field trip (register-rich Q&A stops included), or
 every third tick a YouTube session on the graph's frontier topic (the thin edge of what it
 knows — curiosity chooses the video, the video teaches facts + discourse together).
 2. fetch server-side (urllib, honest UA, size/time caps), strip markup,
 3. swallow through web_expedition.ingest_page — shield → fact candidates → register harvest,
 all existing gates; nothing written to production here.

Every visit is journaled to data/autonomy/roam_journal.jsonl — the monitoring trail.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_JOURNAL = _ROOT / "data" / "autonomy" / "roam_journal.jsonl"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; ATANOR-roamer; research; blueyjkim@gmail.com)"}
_MAX_BYTES = 600_000


def _journal(entry: dict[str, Any]) -> None:
    try:
        _JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with _JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def visit(url: str, *, note: str = "") -> dict[str, Any]:
    """Fetch one page server-side and swallow it through the standard ingest gate."""
    from packages.autonomy_kernel.web_expedition import ingest_page
    try:
        req = urllib.request.Request(url, headers=_UA)
        raw = urllib.request.urlopen(req, timeout=15).read(_MAX_BYTES)
        html = raw.decode("utf-8", "ignore")
    except Exception as exc:
        rep = {"url": url, "ok": False, "error": str(exc)[:120], "note": note}
        _journal({"kind": "visit_failed", **rep})
        return rep
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)[:20_000]
    rep = ingest_page(url, text)
    out = {"url": url, "ok": True, "note": note,
           "fact_candidates": int(rep.get("candidates") or 0),
           "register_harvested": int(rep.get("register_harvested") or 0),
           "injection_blocked": bool(rep.get("injection_blocked"))}
    _journal({"kind": "visit", **out})
    return out


def roam_tick(*, now: float | None = None) -> dict[str, Any]:
    """One autonomous outing. Field trip by default; every 3rd tick a YouTube session on the
    frontier topic (the richest single medium — facts + reactions + dialogue in one context)."""
    now = now if now is not None else time.time()
    cfg_path = _ROOT / "runtime" / "autonomy" / "server_roamer.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {"ticks": 0}
    cfg["ticks"] = int(cfg.get("ticks", 0)) + 1
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    except Exception:
        pass

    if cfg["ticks"] % 3 == 0:                                  # YouTube outing
        try:
            from packages.autonomy_kernel.intrinsic_drive import _frontier_topic
            topic = _frontier_topic()
        except Exception:
            topic = "오늘 하루"
        try:
            from packages.autonomy_kernel.youtube_learn import learn
            reports = learn(f"ytsearch1:{topic}")
            rep = reports[0] if reports else {"error": "no_video"}
            out = {"kind": "youtube", "topic": topic, **{k: rep.get(k) for k in
                   ("video", "comments", "toxic_blocked", "register", "dialogue_pairs",
                    "fact_candidates", "error") if k in rep}}
            _journal(out)
            return out
        except Exception as exc:
            out = {"kind": "youtube_failed", "topic": topic, "error": str(exc)[:120]}
            _journal(out)
            return out

    try:
        from packages.autonomy_kernel.browse_director import _FIELD_TRIPS
        idx = cfg["ticks"] % len(_FIELD_TRIPS)
        _dom, url, label = _FIELD_TRIPS[idx]
        return {"kind": "field_trip", "label": label, **visit(url, note=label)}
    except Exception as exc:
        out = {"kind": "roam_failed", "error": str(exc)[:120]}
        _journal(out)
        return out


def status(last: int = 10) -> dict[str, Any]:
    """Monitoring view: recent visits + bank sizes."""
    rows: list[dict[str, Any]] = []
    try:
        for ln in _JOURNAL.read_text(encoding="utf-8").splitlines()[-last:]:
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        pass
    try:
        from packages.autonomy_kernel.register_harvest import bank_status
        bank = bank_status()
    except Exception:
        bank = {}
    pairs = 0
    try:
        pairs = sum(1 for _ in (_ROOT / "data" / "register_bank" / "discourse_pairs.jsonl")
                    .open(encoding="utf-8"))
    except Exception:
        pass
    return {"recent": rows, "register_bank": bank, "dialogue_pairs": pairs}
