# -*- coding: utf-8 -*-
"""Graph regions — a book is not dissolved into the mass, it is its own BUNDLE.

Owner's design (2026-07-09): " ,
 ? Graph Hub
 , ."

So every ingested source (a book, a paper, a dataset, the web firehose, the core)
registers a REGION: a named, colored partition. Nodes still connect across regions
— knowledge is one graph — but each node remembers which bundle it entered from,
and the visualization can tint by region. This is the provenance backbone for
'read a book -> a distinct district lights up in the mind', and it doubles as
honest lineage (which source a fact came from).

The registry is a small manifest; colors are assigned deterministically so a
region keeps its hue across restarts. Promotion/ingest stamps ``region`` on what
it writes; the graph read-model joins region -> color here.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

MANIFEST = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "graph_regions.jsonl"

# a legible, distinct palette (colour-blind-friendly-ish); index by insertion order,
# then fall back to a hashed hue so we never run out.
_PALETTE = ["#4C9BE8", "#E8734C", "#5CC98B", "#C86BE0", "#E8C24C", "#4CD6D6",
            "#E86B9B", "#9B8BE8", "#8BC34A", "#E0A24C"]
# reserved anchors so the base graph and firehose always read the same colour
_RESERVED = {"core": "#7A8699", "web": "#6BA3E0"}


def _slug(text: str) -> str:
    return re.sub(r"[^\w가-힣]+", "_", text or "").strip("_").lower()[:60] or "region"


def _hashed_color(region_id: str) -> str:
    h = 0
    for ch in region_id:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    # HSL(hue, 62%, 60%) -> hex, mid-saturation so tints read against a dark field
    import colorsys
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.60, 0.62)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def _rows() -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        return []
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _write(rows: list[dict[str, Any]]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")


def _color_for(region_id: str, existing: list[dict[str, Any]]) -> str:
    if region_id in _RESERVED:
        return _RESERVED[region_id]
    used = {r.get("color") for r in existing}
    for c in _PALETTE:
        if c not in used:
            return c
    return _hashed_color(region_id)


def register_region(region_id: str, label: str, kind: str = "book",
                    source: str = "", **meta: Any) -> dict[str, Any]:
    """Create or update a region (idempotent by region_id). Assigns a stable
    colour on first sight. kind ∈ {book, paper, dataset, web, core}."""
    region_id = _slug(region_id)
    rows = _rows()
    by_id = {r.get("region_id"): r for r in rows}
    existing = by_id.get(region_id)
    if existing:
        existing.update({"label": label or existing.get("label"), "kind": kind,
                         "source": source or existing.get("source"),
                         "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta})
        region = existing
    else:
        region = {"region_id": region_id, "label": label or region_id, "kind": kind,
                  "source": source, "color": _color_for(region_id, rows),
                  "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta}
        rows.append(region)
    _write(rows)
    return region


def list_regions() -> list[dict[str, Any]]:
    """All registered regions with their colours — the legend the graph viz tints
    nodes by. Always includes the reserved core/web anchors."""
    rows = _rows()
    have = {r.get("region_id") for r in rows}
    for rid, col in _RESERVED.items():
        if rid not in have:
            rows.append({"region_id": rid, "label": rid.title(), "kind": rid,
                         "source": "", "color": col})
    return rows


def color_of(region_id: str) -> str:
    region_id = _slug(region_id)
    for r in list_regions():
        if r.get("region_id") == region_id:
            return str(r.get("color"))
    return _hashed_color(region_id)
