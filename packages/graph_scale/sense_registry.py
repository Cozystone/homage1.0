# -*- coding: utf-8 -*-
"""STAGE 4 — the sense-keyed READ layer (versioned view, not a store rewrite).

The end state of the sense-disease repair is knowledge keyed by SENSE, not by
surface string. The semantic requirement is met by a RESOLUTION LAYER: a
versioned registry (like the phase space's pointer artifacts) mapping each hub
term to its sense clusters with their edge assignments; consumers resolve
through it, so every reading is sense-scoped even though the physical columns
still carry surface ids. Physically rewriting 25M rows to sense ids is an
OPERATOR-GATED optimization on top — it changes performance, not semantics.

Build: stages 1(trust)+2(partition) run over the hub working set and the
result persists as data/graph_scale/sense_registry/registry_v<ts>.json behind
a current.json pointer (same Windows-lock-safe scheme the phase space uses)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

REG_DIR = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "sense_registry"
CURRENT = REG_DIR / "current.json"

_CACHE: dict[str, Any] = {"data": None, "key": None}


def build_registry(store: Any, *, max_hubs: int = 500,
                   log: Any = print) -> dict[str, Any]:
    """Run trust-filter + partition over the top hubs and persist the registry."""
    from .sense_partition import partition_parents
    from .sense_trust_filter import find_hubs

    hubs = find_hubs(store, max_hubs=max_hubs)
    reg: dict[str, Any] = {}
    t0 = time.time()
    for i, h in enumerate(hubs):
        clusters = partition_parents(store, h)
        if len(clusters) >= 2 or (clusters and clusters[0]["size"] >= 2):
            reg[h] = [{"sense_id": c["sense_id"], "gloss": c["gloss"],
                       "parents": c["parents"][:24]} for c in clusters[:8]]
        if i and i % 100 == 0:
            log(f"  ...{i}/{len(hubs)} hubs ({time.time() - t0:.0f}s)")
    ver = time.strftime("%Y%m%d%H%M%S")
    REG_DIR.mkdir(parents=True, exist_ok=True)
    path = REG_DIR / f"registry_v{ver}.json"
    path.write_text(json.dumps({"built_at": ver, "hubs": len(reg), "terms": reg},
                               ensure_ascii=False), encoding="utf-8")
    tmp = CURRENT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"registry": path.name}), encoding="utf-8")
    os.replace(tmp, CURRENT)
    for old in sorted(REG_DIR.glob("registry_v*.json"))[:-3]:
        try:
            old.unlink()
        except OSError:
            pass
    _CACHE["data"] = None
    return {"hubs_scanned": len(hubs), "hubs_registered": len(reg),
            "seconds": round(time.time() - t0, 1), "artifact": path.name}


def register_terms(store: Any, terms: list[str]) -> dict[str, Any]:
    """Incremental registration: partition SPECIFIC terms (known disease sites
    below the top-hub cutoff — capital sat at rank >300) and merge them into a
    new registry version. Same artifact scheme as build_registry."""
    from .sense_partition import partition_parents

    data = _load()
    reg = dict((data.get("terms") or {}))
    added = []
    for t in terms:
        clusters = partition_parents(store, t)
        if clusters:
            reg[t] = [{"sense_id": c["sense_id"], "gloss": c["gloss"],
                       "parents": c["parents"][:24]} for c in clusters[:8]]
            added.append(t)
    ver = time.strftime("%Y%m%d%H%M%S")
    REG_DIR.mkdir(parents=True, exist_ok=True)
    path = REG_DIR / f"registry_v{ver}.json"
    path.write_text(json.dumps({"built_at": ver, "hubs": len(reg), "terms": reg},
                               ensure_ascii=False), encoding="utf-8")
    tmp = CURRENT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"registry": path.name}), encoding="utf-8")
    os.replace(tmp, CURRENT)
    _CACHE["data"] = None
    return {"registered": added, "total": len(reg), "artifact": path.name}


def _load() -> dict[str, Any]:
    try:
        if not CURRENT.exists():
            return {}
        name = json.loads(CURRENT.read_text(encoding="utf-8"))["registry"]
        path = REG_DIR / name
        key = f"{name}:{path.stat().st_mtime}"
        if _CACHE["key"] != key:
            _CACHE["data"] = json.loads(path.read_text(encoding="utf-8"))
            _CACHE["key"] = key
        return _CACHE["data"] or {}
    except Exception:
        return {}


def senses_of(term: str) -> list[dict[str, Any]]:
    """The registered sense clusters of a term ([] = not a hub / one reading)."""
    return (_load().get("terms") or {}).get(term, [])


def sense_scoped_parents(term: str, context_words: set[str] | None = None) -> list[str]:
    """Resolution API: the is_a parents of the CONTEXT-SELECTED sense (or the
    dominant sense without context) — the sense-keyed read consumers use in
    place of raw parent lists."""
    clusters = senses_of(term)
    if not clusters:
        return []
    if context_words:
        for c in clusters:
            hay = " ".join(c["parents"]) + " " + (c.get("gloss") or "")
            if any(w in hay for w in context_words):
                return c["parents"]
    return clusters[0]["parents"]
