# -*- coding: utf-8 -*-
"""Visual memory v0 — perceptual grounding, the honest first slice.

Owner's vision: like a human eye, the autonomous loop should LEARN what things
LOOK like while it explores — so ' ?' can later be answered by
RECONSTRUCTING the remembered scene as particles, not by reciting a caption.

v0 is deliberately model-free and honest about what it knows:
 learn_visual(concept) — fetch real images via the local SearXNG (images
 category, keyless), decode, and MEASURE a scene signature: vertical color
 bands (sky/mid/ground composition), dominant palette, luminance, edge
 energy (texture). Every signature stores its source image URLs.
 recall_scene(concept) — turn the remembered signature into particle-field
 parameters (band colors, density from texture, motion from edge energy)
 that the SPLATRA/interference-style renderers can play.

Nothing is generated from imagination: the palette IS the measured palette of
real photos of the concept, provenance attached. Depth-Pro-class geometric
understanding is the Ultimate vision track (docs/ultimate-vision/); this v0
gives the color/composition layer of the same pipeline TODAY, No-LLM.
"""
from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
VISUAL_DIR = REPO / "data" / "perception" / "visual_memory"
_SEARX = "http://127.0.0.1:8888"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ATANOR-Perception/0.1"


def _image_urls(concept: str, count: int = 4) -> list[str]:
    url = (_SEARX + "/search?" + urllib.parse.urlencode(
        {"q": concept, "format": "json", "categories": "images"}))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return []
    out = []
    for row in data.get("results", []):
        src = str(row.get("img_src") or row.get("thumbnail_src") or "")
        if src.startswith("http"):
            out.append(src)
        if len(out) >= count:
            break
    return out


def _decode(url: str) -> np.ndarray | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(3_000_000)
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((160, 160))
        return np.asarray(img, dtype=np.float32) / 255.0
    except Exception:
        return None


def signature_from_pixels(px: np.ndarray) -> dict[str, Any]:
    """Measured scene signature from one image array (H,W,3 in [0,1])."""
    h = px.shape[0]
    bands = []
    for lo, hi in ((0, h // 3), (h // 3, 2 * h // 3), (2 * h // 3, h)):
        seg = px[lo:hi].reshape(-1, 3)
        bands.append([round(float(c), 3) for c in seg.mean(axis=0)])
    # dominant palette: coarse 3-bit RGB histogram, top cells
    q = (px.reshape(-1, 3) * 3.999).astype(int)
    keys, counts = np.unique(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], return_counts=True)
    top = keys[np.argsort(-counts)[:4]]
    palette = [[round((int(k) // 16) / 3, 3), round(((int(k) % 16) // 4) / 3, 3),
                round((int(k) % 4) / 3, 3)] for k in top]
    gray = px.mean(axis=2)
    edge = float(np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean())
    return {"bands": bands, "palette": palette,
            "luminance": round(float(gray.mean()), 3),
            "edge_energy": round(edge, 4)}


def learn_visual(concept: str, count: int = 4, log: Any = print) -> dict[str, Any]:
    """Fetch + measure real images of the concept; store the averaged signature
    with source URLs. Returns the stored record (or {} when nothing decodable)."""
    urls = _image_urls(concept, count)
    sigs, kept = [], []
    for u in urls:
        px = _decode(u)
        if px is not None and px.size:
            sigs.append(signature_from_pixels(px))
            kept.append(u)
            log(f"  시각: {concept} <- {u[:70]}")
    if not sigs:
        return {}
    avg = {
        "bands": np.mean([s["bands"] for s in sigs], axis=0).round(3).tolist(),
        "palette": sigs[0]["palette"],  # representative photo's palette
        "luminance": round(float(np.mean([s["luminance"] for s in sigs])), 3),
        "edge_energy": round(float(np.mean([s["edge_energy"] for s in sigs])), 4),
    }
    record = {"concept": concept, "signature": avg, "sources": kept,
              "images_measured": len(sigs), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    (VISUAL_DIR / f"{_key(concept)}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8")
    # Phase 4-4: the measurement becomes KG triples THE MOMENT it exists
    # (visual-KG anchoring) and a dated event on the universal timeline.
    # Both best-effort — a store hiccup never loses the visual memory itself.
    try:
        from .visual_kg import anchor_visual_triples

        anchor_visual_triples(concept)
    except Exception:
        pass
    try:
        from packages.episodic_memory.timeline import record_event

        record_event("ATANOR", "시각측정", concept,
                     note=f"{len(sigs)}장 실측", source="perception")
    except Exception:
        pass
    return record


def _key(concept: str) -> str:
    import hashlib

    # STABLE key — python's str hash is per-process randomized (PYTHONHASHSEED),
    # which made memories written by one process invisible to the server (measured)
    return hashlib.sha256(concept.encode("utf-8")).hexdigest()[:12]


def _load(concept: str) -> dict[str, Any] | None:
    p = VISUAL_DIR / f"{_key(concept)}.json"
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec if rec.get("concept") == concept else None
    except Exception:
        return None


def recall_scene(concept: str) -> dict[str, Any] | None:
    """Particle-field parameters from the remembered signature: three horizontal
    color bands (the composition real photos of the concept actually have),
    particle density from texture, drift from edge energy. Honest provenance."""
    rec = _load(concept)
    if not rec:
        return None
    sig = rec["signature"]
    return {
        "kind": "visual_recall",
        "concept": concept,
        "bands": sig["bands"],            # top/mid/bottom mean colors (measured)
        "palette": sig["palette"],
        "particle_density": min(1.0, 0.3 + sig["edge_energy"] * 6),
        "drift": min(1.0, sig["edge_energy"] * 4),
        "luminance": sig["luminance"],
        "sources": rec["sources"],
        "measured_from": rec["images_measured"],
        "honest_scope": "color_composition_v0 (depth geometry = Ultimate vision track)",
    }


def visual_status() -> dict[str, Any]:
    n = len(list(VISUAL_DIR.glob("*.json"))) if VISUAL_DIR.exists() else 0
    return {"concepts_with_visual_memory": n}
