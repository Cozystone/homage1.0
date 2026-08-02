# -*- coding: utf-8 -*-
"""Spatial Memory Replay Core (v0) — the smart-glasses memory kernel.

The owner's second Jarvis axis (2026-07-12): the eye sees a room; later the human says " 
?" and ATANOR REBUILDS that space — the objects where they were — as 3D particles in the orb.

Kernel contract (honors the BINDING no-frame rule of the whole perception lane):
 * we NEVER store a camera frame. A snapshot is only DISTILLED geometry — each object's label, its
 normalized position (bbox center x,y in [0,1] + a coarse depth) and, if present, its geometric
 signature vector (the same signature_similarity currency the visual cortex already uses);
 * snapshots land on an episodic spatial ledger (data/perception/spatial_memory.jsonl, bounded);
 * on recall, the recorded layout is REBUILT into a SPLATRA scene — objects placed where they were,
 not on a generic ring. Grounded in what was actually seen; empty when nothing was recorded.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from packages.imagination.scene_compiler import _archetype, _hue
from packages.imagination.splatra_cloud import shape_spec as _shape_spec

_LEDGER = Path(__file__).resolve().parents[2] / "data" / "perception" / "spatial_memory.jsonl"
_MAX_SNAPSHOTS = 500


def _load() -> list[dict[str, Any]]:
    try:
        with _LEDGER.open("r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
    except Exception:
        return []


def record_snapshot(objects: list[dict[str, Any]], *, place: str | None = None,
                    lat: float | None = None, lon: float | None = None) -> dict[str, Any]:
    """Record ONE spatial memory: the objects seen and WHERE (distilled geometry only, no frame).
    objects: [{"label", "x"(0..1), "y"(0..1), optional "depth"(0..1), optional "signature":[...]}].
    Optional lat/lon joins the macro-geo layer: the snapshot binds to the nearest anchored place."""
    clean: list[dict[str, Any]] = []
    for o in objects or []:
        label = str(o.get("label") or "").strip()
        if not label:
            continue
        entry = {
            "label": label[:40],
            "x": max(0.0, min(1.0, float(o.get("x", 0.5)))),
            "y": max(0.0, min(1.0, float(o.get("y", 0.5)))),
            "depth": max(0.0, min(1.0, float(o.get("depth", 0.5)))),
            # a geometric signature (not pixels) — the recall currency, trimmed
            "signature": [round(float(v), 4) for v in (o.get("signature") or [])][:64] or None,
        }
        # size (bbox area fraction) — a lesson the reconstruction audit named: without it a replayed
        # laptop and cup rebuild the same size. Optional; absent stays absent (no fabricated size).
        if o.get("size") is not None:
            entry["size"] = max(0.0, min(1.0, float(o.get("size", 0.0))))
        # hue (dominant colour 0..360) — the NEXT audit lesson: a red bottle should replay red, not
        # a label-hashed colour. A negative hue means the crop was essentially grey (no confident
        # colour) → stays absent, so the replay falls back to the label hue rather than fabricating one.
        if o.get("hue") is not None and float(o.get("hue")) >= 0:
            entry["hue"] = round(float(o.get("hue")) % 360, 1)
        clean.append(entry)
    snap = {"id": f"snap_{int(time.time() * 1000)}", "at": round(time.time(), 2),
            "place": (place or "").strip()[:60] or None, "objects": clean,
            "frames_stored": 0, "left_device": False}
    if lat is not None and lon is not None:
        snap["lat"], snap["lon"] = round(float(lat), 6), round(float(lon), 6)
        from packages.perception.geo_anchor import bind_snapshot

        snap = bind_snapshot(snap)                    # nearest anchored place names a nameless room
    if not clean:
        return {**snap, "recorded": False}
    try:
        entries = _load()
        entries.append(snap)
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER.open("w", encoding="utf-8") as fh:
            for e in entries[-_MAX_SNAPSHOTS:]:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {**snap, "recorded": True, "n_objects": len(clean)}


def list_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    """Recent snapshots (metadata only: id, place, time, object count) for a recall menu."""
    return [{"id": s["id"], "at": s.get("at"), "place": s.get("place"),
             "n_objects": len(s.get("objects") or [])} for s in _load()[-limit:][::-1]]


def recall_snapshot(snapshot_id: str | None = None, place: str | None = None) -> dict[str, Any] | None:
    """The recorded layout to rebuild — an explicit id, else the latest matching `place`, else the
    most recent. Place match is grounded: only a space actually recorded can be recalled."""
    snaps = _load()
    if not snaps:
        return None
    if snapshot_id:
        return next((s for s in snaps if s.get("id") == snapshot_id), None)
    if place:
        pl = place.replace(" ", "")
        matches = [s for s in snaps if pl and pl in str(s.get("place") or "").replace(" ", "")]
        if matches:
            return matches[-1]
    return snaps[-1]


# recall-intent cues (routing, not knowledge): a phrase asking to SEE a remembered space. Phrase-

_RECALL_CUES = (
    "그때 그 방", "그 방 보여", "아까 본 방", "아까 봤던", "봤던 방", "봤던 공간", "본 방 보여",
    "방 보여줘", "방 보여 줘", "공간 보여줘", "공간 보여 줘", "배치 보여", "그 공간 보여",
    "방 재현", "공간 재현", "재현해줘", "그때 그 공간", "어디 있었", "어디에 있었", "다시 보여줘",
    "the room i saw", "show me the room", "replay the space", "the space i saw", "where was it",
)


def detect_spatial_recall(query: str) -> dict[str, Any]:
    """Does this ask to REPLAY a remembered space? If so, which place (if the query names one that
    was actually recorded)? Honest routing: {is_recall, place} — place None means the latest space."""
    q = str(query or "").lower()
    is_recall = any(cue in q for cue in _RECALL_CUES)
    place = None
    if is_recall:
        for s in _load():
            p = str(s.get("place") or "").strip()
            if p and p.lower() in q:
                place = p          # a recorded place named in the query
                break
    return {"is_recall": is_recall, "place": place}


def reconstruct_scene(snapshot: dict[str, Any] | None, *, duration: float = 6.0) -> dict[str, Any]:
    """Rebuild a recorded space as a SPLATRA scene — each object at WHERE it was seen (bbox center
    → a unit-cube position), shaped by its label. This is spatial replay, not a generic layout."""
    objs = (snapshot or {}).get("objects") or []
    if not objs:
        return {"objects": [], "links": [], "motion": [], "duration": 0.0,
                "meta": {"empty": True, "replay": True}}
    scene_objects: list[dict[str, Any]] = []
    motion: list[dict[str, Any]] = []
    t = 0.0
    for i, o in enumerate(objs):
        oid = f"{o['label']}#{i}"
        # bbox center (x right, y down in [0,1]) → scene space (x right, y UP, z from depth) in [-1,1]
        pos = [round(o["x"] * 2 - 1, 4), round(1 - o["y"] * 2, 4), round(o.get("depth", 0.5) * 2 - 1, 4)]
        entry: dict[str, Any] = {
            "id": oid, "label": o["label"], "archetype": _archetype({"label": o["label"]}),
            "pos": pos, "scale": round(0.8 - 0.25 * o.get("depth", 0.5), 3),   # nearer = bigger
            # a RECORDED colour replays true; without one, the label hue is an honest fallback
            "hue": round(float(o["hue"]), 1) if o.get("hue") is not None else _hue(o["label"]),
            "role": "memory",
            "shape": _shape_spec({"label": o["label"]}),   # replayed rooms get silhouettes too
        }
        if o.get("size") is not None:                       # recorded size scales the rebuilt object
            entry["size"] = round(float(o["size"]), 4)
            entry["scale"] = round(entry["scale"] * (0.6 + 1.6 * min(1.0, float(o["size"]) * 3)), 3)
        scene_objects.append(entry)
        motion.append({"t": round(t, 3), "target": oid, "action": "appear"})
        t += min(0.4, (duration * 0.5) / max(1, len(objs)))
    return {"objects": scene_objects, "links": [], "motion": motion, "duration": round(duration, 3),
            "meta": {"replay": True, "place": (snapshot or {}).get("place"),
                     "at": (snapshot or {}).get("at"), "n_objects": len(scene_objects), "empty": False}}
