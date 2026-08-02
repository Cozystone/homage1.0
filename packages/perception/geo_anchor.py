# -*- coding: utf-8 -*-
"""Macro-geo spatial binding (v0) — pin a remembered SPACE to a place on Earth.

The owner's fusion plan (2026-07-12): break perception out of the egocentric frame by joining
first-person spatial memory to a world coordinate system. This kernel is the doctrine-clean core:

 * a GEO ANCHOR is a SYMBOLIC node — name + lat/lon (+ optional address), a permanent graph
 symbol a snapshot can bind to (" ", not pixels);
 * spatial snapshots may carry a {lat, lon}; recall can then answer " ?" with a place
 on the map, and a nameless snapshot inherits the NEAREST anchor's name (grounded, radius-bound);
 * NO Google Maps scraping — that violates their ToS and poisons the project's honesty. The open
 source of truth is OpenStreetMap; its network resolver is OFF by default (ATANOR_GEO_OSM=1
 opt-in) and absence is reported honestly (None), never fabricated.

Pure Python + stdlib; ledger-bounded; offline-testable. The same no-frame doctrine applies: an
anchor stores WHERE and WHAT-CALLED, never imagery.
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

_LEDGER = Path(__file__).resolve().parents[2] / "data" / "perception" / "geo_anchors.jsonl"
_MAX_ANCHORS = 2000
_EARTH_R = 6371000.0


def _load() -> list[dict[str, Any]]:
    try:
        with _LEDGER.open("r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
    except Exception:
        return []


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters — the binding currency between a sighting and an anchor."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


def anchor_place(name: str, lat: float, lon: float, *, address: str | None = None,
                 source: str = "manual") -> dict[str, Any]:
    """Mint (or refresh) a symbolic geo node. Same name re-anchored → position/address updated,
    never duplicated — a place is ONE node however many times it is seen."""
    name = str(name or "").strip()[:80]
    if not name:
        return {"anchored": False, "reason": "no_name"}
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"anchored": False, "reason": "bad_coords"}
    anchors = _load()
    entry = next((a for a in anchors if a.get("name") == name), None)
    if entry is None:
        entry = {"id": f"geo_{int(time.time() * 1000)}", "name": name}
        anchors.append(entry)
    entry.update({"lat": round(lat, 6), "lon": round(lon, 6),
                  "address": (str(address).strip()[:160] or None) if address else entry.get("address"),
                  "source": str(source)[:40], "at": round(time.time(), 2),
                  "times_seen": int(entry.get("times_seen", 0)) + 1})
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER.open("w", encoding="utf-8") as fh:
            for a in anchors[-_MAX_ANCHORS:]:
                fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {**entry, "anchored": True}


def nearest_anchor(lat: float, lon: float, *, max_m: float = 120.0) -> dict[str, Any] | None:
    """The closest anchored place within the radius — or an honest None. The radius is deliberately
    tight (~a building) so a snapshot never inherits a wrong neighbourhood's name."""
    best, best_d = None, float("inf")
    for a in _load():
        try:
            d = haversine_m(lat, lon, float(a["lat"]), float(a["lon"]))
        except Exception:
            continue
        if d < best_d:
            best, best_d = a, d
    if best is not None and best_d <= max_m:
        return {**best, "distance_m": round(best_d, 1)}
    return None


def list_anchors(limit: int = 50) -> list[dict[str, Any]]:
    return _load()[-limit:][::-1]


def resolve_address(lat: float, lon: float) -> dict[str, Any] | None:
    """Reverse-geocode via OpenStreetMap Nominatim — OPT-IN network (ATANOR_GEO_OSM=1) with the
    project's honest User-Agent, else None. Google Maps scraping is refused on ToS grounds."""
    if os.environ.get("ATANOR_GEO_OSM") != "1":
        return None
    try:
        import urllib.parse
        import urllib.request

        url = ("https://nominatim.openstreetmap.org/reverse?format=jsonv2&"
               + urllib.parse.urlencode({"lat": lat, "lon": lon}))
        req = urllib.request.Request(url, headers={
            "User-Agent": "ATANOR-AlphaFramer/0.1 (geo anchor; blueyjkim@gmail.com)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            j = json.loads(r.read().decode("utf-8"))
        name = j.get("name") or (j.get("address") or {}).get("building") or ""
        return {"address": j.get("display_name"), "name": name or None, "source": "osm"}
    except Exception:
        return None


def bind_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Join one spatial snapshot to the geo layer: a snapshot carrying {lat, lon} gains the nearest
    anchored place's name (when it has none) and the anchor reference. Grounded or untouched —
    a snapshot without coordinates simply stays egocentric, honestly."""
    lat, lon = snapshot.get("lat"), snapshot.get("lon")
    if lat is None or lon is None:
        return snapshot
    hit = nearest_anchor(float(lat), float(lon))
    if hit is None:
        return snapshot
    out = dict(snapshot)
    out["geo"] = {"anchor": hit["name"], "distance_m": hit["distance_m"],
                  "lat": hit["lat"], "lon": hit["lon"], "address": hit.get("address")}
    if not out.get("place"):
        out["place"] = hit["name"]                     # a nameless room inherits its building's name
    return out
