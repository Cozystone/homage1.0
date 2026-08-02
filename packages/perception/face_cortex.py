# -*- coding: utf-8 -*-
"""The visual cortex — face perception + GEOMETRIC identity, on-device, honest.

DeepFace (serengil/deepface) is the pluggable recognition core: it detects faces and
returns an embedding + soft attributes (emotion/age). When DeepFace is not installed the
cortex says so HONESTLY and returns no recognition — it never fabricates a face or a name.

Identity is resolved GEOMETRICALLY, the same way visual_kg matches a bottle instance: an
embedding is compared by cosine similarity to the LEARNED face signatures (data the owner
taught), and a match counts only above a threshold. There is NO name table in code — an
unknown face is an honest GAP, recorded as a genuine unknown entity, never guessed. The owner
teaches a face by name; that is the only way a name is ever attached.

Nothing here stores a frame. `perceive()` takes pixels, returns the DISTILLED perception, and
the caller records only that — the frame is discarded (the life-log stays an event log, not a
photo album).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
KNOWN_FACES_PATH = _REPO / "data" / "perception" / "known_faces.jsonl"

# cosine-similarity threshold for "this is a known person". Deliberately conservative: a miss
# (an honest "I don't recognize you") is a dignified gap; a false match (calling a stranger by
# the owner's name) is a fabrication and far worse.
_MATCH_THRESHOLD = 0.62
_MODEL_NAME = "Facenet"          # 128-d embedding; light enough for CPU when DeepFace is present


# ── pluggable DeepFace core ──────────────────────────────────────────────────────────────────
_DF_CACHE: dict[str, Any] = {"tried": False, "mod": None}


def _deepface() -> Any | None:
    if not _DF_CACHE["tried"]:
        _DF_CACHE["tried"] = True
        try:
            from deepface import DeepFace  # type: ignore

            _DF_CACHE["mod"] = DeepFace
        except Exception:
            _DF_CACHE["mod"] = None
    return _DF_CACHE["mod"]


def core_available() -> bool:
    return _deepface() is not None


def analyze_pixels(rgb: np.ndarray) -> list[dict[str, Any]]:
    """Faces in one RGB image (H,W,3 in 0..255) via DeepFace: each carries a unit-norm
    embedding + soft attributes. Empty list when no face is found OR the core is absent
    (the caller distinguishes the two via core_available())."""
    df = _deepface()
    if df is None:
        return []
    faces: list[dict[str, Any]] = []
    try:
        reps = df.represent(rgb, model_name=_MODEL_NAME, enforce_detection=False,
                            detector_backend="opencv")
    except Exception:
        return []
    for rep in reps or []:
        vec = np.asarray(rep.get("embedding") or [], dtype=np.float32)
        if vec.size == 0:
            continue
        n = float(np.linalg.norm(vec)) or 1.0
        entry: dict[str, Any] = {"embedding": (vec / n).tolist(), "region": rep.get("facial_area")}
        try:                     # attributes are best-effort — a face without them still counts
            an = df.analyze(rgb, actions=("emotion", "age"), enforce_detection=False,
                            detector_backend="opencv", silent=True)
            a0 = an[0] if isinstance(an, list) else an
            entry["emotion"] = str(a0.get("dominant_emotion") or "")
            entry["age"] = int(a0.get("age") or 0) or None
        except Exception:
            pass
        faces.append(entry)
    return faces


# ── learned face store (DATA, not a code table) ─────────────────────────────────────────────
def _load_known() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in KNOWN_FACES_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def teach_face(name: str, embedding: list[float]) -> dict[str, Any]:
    """Attach a NAME to a face embedding — the only way a name ever enters the system. Averages
    into an existing person so their signature sharpens over repeated teachings."""
    name = str(name or "").strip()
    vec = np.asarray(embedding, dtype=np.float32)
    if not name or vec.size == 0:
        return {"taught": False, "reason": "empty"}
    n = float(np.linalg.norm(vec)) or 1.0
    vec = vec / n
    known = _load_known()
    merged = False
    for k in known:
        if str(k.get("name")) == name:
            old = np.asarray(k.get("embedding"), dtype=np.float32)
            avg = old * k.get("n", 1) + vec
            k["embedding"] = (avg / (float(np.linalg.norm(avg)) or 1.0)).tolist()
            k["n"] = int(k.get("n", 1)) + 1
            k["taught_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            merged = True
            break
    if not merged:
        known.append({"name": name, "embedding": vec.tolist(), "n": 1,
                      "taught_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    KNOWN_FACES_PATH.parent.mkdir(parents=True, exist_ok=True)
    KNOWN_FACES_PATH.write_text("\n".join(json.dumps(k, ensure_ascii=False) for k in known)
                                + ("\n" if known else ""), encoding="utf-8")
    return {"taught": True, "name": name, "samples": next(k["n"] for k in known if k["name"] == name)}


def resolve_identity(embedding: list[float]) -> dict[str, Any]:
    """Geometric identity: nearest learned face by cosine similarity, above threshold. Returns
    {identity: name|None, familiarity: 0..1}. No match → honest gap (identity None)."""
    vec = np.asarray(embedding, dtype=np.float32)
    known = _load_known()
    if vec.size == 0 or not known:
        return {"identity": None, "familiarity": 0.0}
    best_name, best_sim = None, -1.0
    for k in known:
        kv = np.asarray(k.get("embedding"), dtype=np.float32)
        if kv.size != vec.size:
            continue
        sim = float(np.dot(vec, kv))     # both unit-norm → cosine similarity
        if sim > best_sim:
            best_sim, best_name = sim, str(k.get("name"))
    familiarity = round(max(0.0, best_sim), 3)
    return {"identity": best_name if best_sim >= _MATCH_THRESHOLD else None,
            "familiarity": familiarity}


def perceive(rgb: np.ndarray) -> dict[str, Any]:
    """The full honest face perception for one frame. Never fabricates: an unrecognized face
    is reported as a gap (identity None, unknown_present True), and when the core is missing
    the perception says so instead of pretending to see."""
    if not core_available():
        return {"core": "absent", "faces": [], "person_present": False,
                "unknown_present": False,
                "note": "얼굴 인식 코어(DeepFace)가 아직 설치되지 않았어요 — 지금은 얼굴을 못 봅니다."}
    faces_raw = analyze_pixels(rgb)
    faces: list[dict[str, Any]] = []
    unknown = False
    for f in faces_raw:
        res = resolve_identity(f.get("embedding") or [])
        if res["identity"] is None:
            unknown = True
        faces.append({"identity": res["identity"], "familiarity": res["familiarity"],
                      "emotion": f.get("emotion") or None, "age": f.get("age"),
                      "embedding": f.get("embedding")})   # embedding returned so caller can TEACH
    return {"core": "deepface", "faces": faces,
            "person_present": bool(faces), "unknown_present": unknown}
