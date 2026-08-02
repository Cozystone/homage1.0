# -*- coding: utf-8 -*-
"""Perception stream API — the local context ledger the orb reads and the daemon feeds.

POST /api/perception/ingest  {app, window_title}  -> distill + record (raw discarded)
GET  /api/perception/status                        -> events, redactions, interests
GET  /api/perception/interests                     -> recency-weighted current context
POST /api/perception/clear                         -> wipe the ledger (user owns it)
POST /api/perception/tick                          -> probe the active window once (Linux)

The ingest endpoint accepts observations from ANY source (the OS daemon, a browser
extension) — the atomic-ingestion contract. It NEVER stores the raw title or a
screenshot; only concepts + app + time land in the ledger, and nothing leaves 127.0.0.1.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.perception_stream import ContextLedger, ProbeUnavailable, distill_activity

router = APIRouter(prefix="/api/perception", tags=["perception"])

_LEDGER_PATH = Path(__file__).resolve().parents[4] / "data" / "perception" / "context_ledger.jsonl"
_LEDGER = ContextLedger(_LEDGER_PATH)


class IngestIn(BaseModel):
    app: str = Field(default="unknown", max_length=120)
    window_title: str = Field(default="", max_length=600)


@router.post("/ingest")
def ingest(body: IngestIn) -> dict[str, Any]:
    ev = distill_activity(body.app, body.window_title, time.strftime("%Y-%m-%dT%H:%M:%S"))
    _LEDGER.record(ev)
    # echo back the CONCEPTS only — proving the raw never round-trips
    return {"recorded": True, "app": ev.app, "concepts": ev.concepts,
            "redacted": ev.redacted, "raw_discarded": True, "left_device": False}


@router.post("/tick")
def tick() -> dict[str, Any]:
    from packages.perception_stream.capture import probe_active_window

    try:
        app, title = probe_active_window()
    except ProbeUnavailable as exc:
        return {"probed": False, "reason": str(exc)}
    ev = distill_activity(app, title, time.strftime("%Y-%m-%dT%H:%M:%S"))
    _LEDGER.record(ev)
    return {"probed": True, "app": ev.app, "concepts": ev.concepts, "redacted": ev.redacted}


class Detection(BaseModel):
    label: str = Field(max_length=80)
    score: float = 0.0


class VisualIngestIn(BaseModel):
    detections: list[Detection] = Field(default_factory=list, max_length=32)


# per-label cooldown so a bottle sitting in frame for a minute is ONE event,
# not forty — the timeline stays a life log, not a frame log
_SEEN_COOLDOWN_S = 60.0
_last_seen: dict[str, float] = {}

# presence handshake with the selfhood loop: a person in frame = the user is
# HERE. Written through to disk so the observation survives module reloads.
_PRESENCE_PATH = _LEDGER_PATH.parent / "presence.json"
_PERSON_LABELS = {"사람", "person"}


def _mark_person_seen(*, familiar: bool | None = None, identity: str | None = None) -> None:
    try:
        _PRESENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, Any] = {"person_seen_at": time.time()}
        if familiar is not None:
            rec["familiar"] = bool(familiar)      # face cortex resolved (or failed to)
            rec["identity"] = identity
        _PRESENCE_PATH.write_text(json.dumps(rec), encoding="utf-8")
    except Exception:
        pass


def person_recently_seen(window_s: float = 120.0) -> bool:
    """The selfhood observation's user_present signal (Phase 4-5 x 3-6 wiring):
    True while a camera person-sighting is fresher than the window."""
    try:
        at = float(json.loads(_PRESENCE_PATH.read_text(encoding="utf-8"))["person_seen_at"])
        return (time.time() - at) < window_s
    except Exception:
        return False


def present_person_unfamiliar(window_s: float = 120.0) -> bool:
    """True while a RECENTLY-seen person was NOT recognized by the face cortex — a live
    perceptual gap the selfhood loop can turn into its own curiosity/inquiry (never a
    hard-coded question; the mind surfaces it or stays silent)."""
    try:
        rec = json.loads(_PRESENCE_PATH.read_text(encoding="utf-8"))
        fresh = (time.time() - float(rec["person_seen_at"])) < window_s
        return bool(fresh and rec.get("familiar") is False)
    except Exception:
        return False


def _decode_image(data_url: str):
    """base64 image (data URL or bare) -> RGB uint8 array, or None. Pillow first, cv2 second
    (cv2 ships with the DeepFace stack anyway); no core -> None, honestly."""
    import base64
    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    try:
        blob = base64.b64decode(raw)
    except Exception:
        return None
    try:
        import io

        from PIL import Image  # type: ignore

        return __import__("numpy").asarray(Image.open(io.BytesIO(blob)).convert("RGB"))
    except Exception:
        pass
    try:
        import cv2  # type: ignore
        import numpy as _np

        arr = cv2.imdecode(_np.frombuffer(blob, _np.uint8), cv2.IMREAD_COLOR)
        return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB) if arr is not None else None
    except Exception:
        return None


_AFFORD_COOLDOWN_S = 90.0
_last_afford: dict[str, float] = {"external_at": 0.0}


def _user_state_affordance(perception: dict[str, Any]) -> dict[str, Any] | None:
    """Owner's personalization directive: read the USER'S STATE from the face perception and lay
    the walkable paths (no if/then — resonance). The internal particle path self-expresses (the AI
    moving the field to match the felt state); external paths (asking, soothing) surface cooldowned
    so ATANOR responds to context without nagging. Fails silent — perception must never break."""
    try:
        from packages.affordance.context_affordance import propose
        from packages.imagination.particle_intent import from_state
        from packages.perception.user_state import observe_from_faces

        obs = observe_from_faces(perception)
        if obs is None or not obs.concepts:
            return None
        result = propose(obs)                            # default tier ASSIST
        chosen = result.get("chosen")
        # the field is the AI's expressive body — paint the felt state whenever there's real affect
        # (continuous embodiment, READONLY/autonomous), independent of the external path race
        expressed = False
        if abs(obs.valence) > 0.05 or abs(obs.energy - 0.5) > 0.05:
            from_state(obs.concepts, valence=obs.valence, energy=obs.energy,
                       note="·".join(obs.concepts[:3]), source="face")
            expressed = True
        now = time.time()
        external = [p for p in result.get("paths", [])
                    if p.get("effect") not in ("particle", "silence")]
        surfaced: list[dict[str, Any]] = []
        enacted: dict[str, Any] | None = None
        if external and now - _last_afford["external_at"] >= _AFFORD_COOLDOWN_S:
            _last_afford["external_at"] = now
            surfaced = external[:2]
            # AUTONOMY (owner's real-action frontier): once the operator has raised the trust dial
            # to GUARDED+, an actionable path enacts itself through the gated+audited lane — the same
            # code that only surfaces a proposal at a low tier. The machine never raised its own dial.
            try:
                from packages.affordance.enact import enact, get_lane
                from packages.os_action_lane.models import TrustTier

                if get_lane().tier >= TrustTier.GUARDED:
                    top = next((p for p in external if p.get("has_action")), None)
                    if top:
                        enacted = enact(top["affordance_id"], intent=str(top.get("label", "")))
            except Exception:
                enacted = None
        return {"observed": obs.concepts, "chosen": chosen, "surfaced": surfaced,
                "expressed": expressed, "enacted": enacted}
    except Exception:
        return None


class FaceIngestIn(BaseModel):
    image: str = Field(default="", max_length=8_000_000)   # base64 frame; processed then dropped


@router.post("/face-ingest")
def face_ingest(body: FaceIngestIn) -> dict[str, Any]:
    """The eye: one webcam frame in, a DISTILLED face perception out. The frame is NEVER
    stored — only the recognized identity (or the honest 'unknown') and soft state land on
    the episodic timeline, and the presence handshake carries familiarity so the selfhood
    loop can feel an unrecognized person as a live gap. No name is ever guessed."""
    from packages.perception.face_cortex import core_available, perceive

    if not core_available():
        return {"core": "absent", "faces": [], "recorded": [],
                "note": "얼굴 인식 코어(DeepFace)가 아직 설치되지 않았어요 — 지금은 얼굴을 못 봅니다.",
                "frames_stored": 0, "left_device": False}
    rgb = _decode_image(body.image)
    if rgb is None:
        return {"core": "deepface", "faces": [], "recorded": [], "note": "프레임을 읽지 못했어요.",
                "frames_stored": 0, "left_device": False}

    p = perceive(rgb)
    from packages.episodic_memory.timeline import record_event

    recorded: list[str] = []
    any_unfamiliar = False
    for f in p.get("faces", []):
        ident = f.get("identity")
        state = f.get("emotion") or ""
        if ident:                                        # a known person, geometrically resolved
            record_event(ident, "함께 있음", "카메라",
                         note=f"familiarity={f.get('familiarity')} state={state}", source="face")
            recorded.append(ident)
        else:                                            # an honest gap — a person we don't know
            any_unfamiliar = True
            record_event("ATANOR", "처음 보는 얼굴", "카메라",
                         note=f"familiarity={f.get('familiarity')} state={state}", source="face")
    if p.get("person_present"):
        _mark_person_seen(familiar=not any_unfamiliar,
                          identity=next((f.get("identity") for f in p["faces"] if f.get("identity")), None))
    # strip embeddings of KNOWN faces from the reply; keep them only for unknowns so the page

    faces_out = [{k: v for k, v in f.items() if k != "embedding" or f.get("identity") is None}
                 for f in p.get("faces", [])]
    return {"core": "deepface", "faces": faces_out, "recorded": recorded,
            "unknown_present": p.get("unknown_present", False),
            "affordance": _user_state_affordance(p),
            "frames_stored": 0, "left_device": False}


class SceneIngestIn(BaseModel):
    image: str = Field(max_length=3_000_000)


_SCENE_WEAVE: dict[str, Any] | None = None    # the living scene state (engine-process lifetime)
_SCENE_FRAMES: dict[str, int] = {}            # per-label persistence, for plausibility re-verification
_ATTN_STATE: Any = None                       # predictive attention gate (compute only on change)
_SCENE_LAST_READ: dict[str, Any] | None = None  # last full read, reused when a frame is predicted


def _bump_frames(seen: set[str]) -> None:
    """Count how persistently each label appears: +1 when seen (cap 10), -1 when absent (a brief miss
    doesn't reset it). Re-verification reads this so an implausible/faint object must PERSIST to count."""
    for lb in list(_SCENE_FRAMES) + list(seen):
        if lb in seen:
            _SCENE_FRAMES[lb] = min(_SCENE_FRAMES.get(lb, 0) + 1, 10)
        else:
            n = _SCENE_FRAMES.get(lb, 0) - 1
            if n <= 0:
                _SCENE_FRAMES.pop(lb, None)
            else:
                _SCENE_FRAMES[lb] = n


@router.post("/scene-ingest")
def scene_ingest(body: SceneIngestIn) -> dict[str, Any]:
    """The OPEN-VOCABULARY eye + the LIVING narrative (owner: ).
 One frame in → OWLv2 detects arbitrary named objects (GPU, lazy-loaded) → the scene graph reads
 spatial relations + a commonsense context → the scene WEAVE decides what is worth SAYING: the
 full read on first sight, then only CHANGES ( / / ). The frame is
 distilled and discarded — never stored; only labels, boxes and sentences leave this call."""
    global _SCENE_WEAVE, _ATTN_STATE, _SCENE_LAST_READ
    try:
        from packages.perception import open_vocab
    except Exception:
        return {"core": "absent", "objects": [], "narrative": None,
                "note": "오픈보캐뷸러리 시각 코어를 불러오지 못했어요."}
    if not open_vocab.available():
        return {"core": "absent", "objects": [], "narrative": None,
                "note": "시각 코어(torch/transformers)가 아직 없어요 — 지금은 장면을 못 읽습니다."}
    rgb = _decode_image(body.image)
    if rgb is None:
        return {"core": "owlv2", "objects": [], "narrative": None, "note": "프레임을 읽지 못했어요."}
    try:
        from PIL import Image as _Image

        from packages.perception import attention, scene_weave
        from packages.perception.open_vocab import compose_scene
        from packages.perception.scene_graph import describe_with_relations

        from packages.perception.plausibility import annotate

        img = _Image.fromarray(rgb)


        # Reduce the frame to a tiny retinal code and only run the expensive open-vocab detector
        # when the scene actually changed and settled; otherwise reuse the last read for ~free.
        # A static room ≈ no GPU. The client reads next_interval_s to poll slower when idle.
        if _ATTN_STATE is None:
            _ATTN_STATE = attention.new_state()
        sig = attention.frame_signature(rgb)
        gate = attention.decide(_ATTN_STATE, sig)
        if not gate["run"] and _SCENE_LAST_READ is not None:
            cached = dict(_SCENE_LAST_READ)
            cached.update({"skipped": True, "attention": gate["reason"],
                           "attention_energy": round(gate["energy"], 4),
                           "next_interval_s": gate["next_interval_s"]})
            return cached

        dets = open_vocab.detect(img, threshold=0.25)

        # implausible/faint detections as TENTATIVE until they persist. Only CONFIDENT objects reach
        # the scene sentence + the living narration; tentative ones ride along dimmed for the overlay.
        _bump_frames({d["label_ko"] for d in dets})
        dets = annotate(dets, lambda ko: _SCENE_FRAMES.get(ko, 0))
        confident = [d for d in dets if not d.get("tentative")]
        comp = compose_scene(confident, img.size)
        rel = describe_with_relations(confident, img.size)
        if _SCENE_WEAVE is None:
            _SCENE_WEAVE = scene_weave.new_state()
        weave = scene_weave.observe(_SCENE_WEAVE, [d["label_ko"] for d in confident],
                                    comp["scene_sentence"])
        attention.commit(_ATTN_STATE, sig)                  # this frame is the new prediction baseline
        result = {"core": "owlv2", "objects": dets, "image_size": list(img.size),
                  "scene_sentence": comp["scene_sentence"],
                  "relations_ko": rel["relations_ko"][:4],
                  "commonsense": rel["commonsense"],
                  "narrative": weave["narrative"], "changed": weave["changed"],
                  "living_sentence": weave["last_sentence"],
                  "skipped": False, "attention": gate["reason"],
                  "attention_energy": round(gate["energy"], 4),
                  "next_interval_s": gate["next_interval_s"],
                  "frames_stored": 0, "left_device": False}
        _SCENE_LAST_READ = result
        return result
    except Exception as exc:                                # the eye must never 500 the engine
        try:                                                # diagnostics land in runtime/, never client
            import traceback
            from pathlib import Path as _P
            p = _P(__file__).resolve().parents[3].parent / "runtime" / "perception_scene_error.log"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        return {"core": "owlv2", "objects": [], "narrative": None,
                "note": f"장면 읽기 실패 ({type(exc).__name__})"}


class FaceTeachIn(BaseModel):
    name: str = Field(max_length=60)
    embedding: list[float] = Field(default_factory=list, max_length=1024)


@router.post("/face-teach")
def face_teach(body: FaceTeachIn) -> dict[str, Any]:
    """The owner attaches a NAME to a face the cortex just saw (the only path a name enters).
    Purely local — the embedding is a geometric signature, not a photo."""
    from packages.perception.face_cortex import teach_face

    return teach_face(body.name, body.embedding)


@router.get("/faces")
def faces() -> dict[str, Any]:
    """Who the cortex has been taught — names + sample counts, never embeddings."""
    from packages.perception.face_cortex import _load_known, core_available

    known = _load_known()
    return {"core_available": core_available(),
            "known": [{"name": k.get("name"), "samples": int(k.get("n", 1))} for k in known]}


@router.post("/visual-ingest")
def visual_ingest(body: VisualIngestIn) -> dict[str, Any]:
    """Phase 4-5 v0: the browser page detects objects ON DEVICE and sends ONLY
 labels here (frames never leave the page). Each new sighting lands on the
 universal episodic timeline; possessions old enough trigger the 
 suggestion primitive — grounded in recorded events, or silent."""
    from packages.episodic_memory.timeline import record_event, repurchase_suggestion

    now = time.time()
    recorded: list[str] = []
    suggestions: list[dict[str, Any]] = []
    for det in body.detections:
        label = det.label.strip()
        if not label or det.score < 0.5:
            continue
        if label in _PERSON_LABELS:
            _mark_person_seen()  # presence refreshes every sighting (no cooldown)
        if now - _last_seen.get(label, 0.0) < _SEEN_COOLDOWN_S:
            continue
        _last_seen[label] = now
        record_event("사용자", "목격", label,
                     note=f"카메라 감지 score={det.score:.2f}", source="camera")
        recorded.append(label)
        try:
            s = repurchase_suggestion(label)
            if s:
                suggestions.append(s)
        except Exception:
            continue
    return {"recorded": recorded, "suggestions": suggestions,
            "frames_received": 0, "left_device": False}



_POSTURE_KO = {"standing": "서 있음", "sitting": "앉아 있음", "lying": "누워 있음"}
_GESTURE_KO = {"arms_raised": "팔을 듦", "hand_near_face": "손을 얼굴 가까이", "t_pose": "양팔 벌림",
               # dynamic (motion over time)
               "waving": "손 흔들어 인사", "clapping": "박수", "beckoning": "손짓해 부름"}


class PoseIngestIn(BaseModel):
    posture: str = Field(default="unknown", max_length=40)      # standing | sitting | lying | unknown
    gesture: str | None = Field(default=None, max_length=40)    # arms_raised | hand_near_face | waving | ...
    present: bool = True                                        # a human body is in frame


@router.post("/pose-ingest")
def pose_ingest(body: PoseIngestIn) -> dict[str, Any]:
    """MediaPipe Pose runs IN THE BROWSER; only a DISTILLED posture/gesture reaches here —
    never landmarks, never frames. A body in frame refreshes presence (the WHO stays the face
    lane's job — we don't assert familiarity from a silhouette), and a new posture or gesture
    lands on the episodic timeline so the selfhood loop can feel someone sitting with it."""
    from packages.episodic_memory.timeline import record_event

    posture = (body.posture or "unknown").strip().lower()
    gesture = (body.gesture or "").strip().lower() or None
    if body.present:
        _mark_person_seen()                       # presence only — pose sees a body, not an identity
    now = time.time()
    recorded: list[str] = []
    if posture in _POSTURE_KO and now - _last_seen.get(f"pose:{posture}", 0.0) >= _SEEN_COOLDOWN_S:
        _last_seen[f"pose:{posture}"] = now
        record_event("사용자", "자세", _POSTURE_KO[posture], note="pose (on-device)", source="pose")
        recorded.append(_POSTURE_KO[posture])
    if gesture and gesture in _GESTURE_KO and now - _last_seen.get(f"gesture:{gesture}", 0.0) >= _SEEN_COOLDOWN_S:
        _last_seen[f"gesture:{gesture}"] = now
        record_event("사용자", "제스처", _GESTURE_KO[gesture], note="pose (on-device)", source="pose")
        recorded.append(_GESTURE_KO[gesture])
    return {"recorded": recorded, "posture": posture, "gesture": gesture,
            "landmarks_stored": 0, "frames_received": 0, "left_device": False}


class SpatialObject(BaseModel):
    label: str = Field(max_length=40)
    x: float = 0.5
    y: float = 0.5
    depth: float = 0.5
    size: float | None = None          # bbox area fraction — a reconstruction-audit lesson
    hue: float | None = None           # dominant colour 0..360 — the audit's next lesson (mined)
    signature: list[float] = Field(default_factory=list, max_length=128)


class SpatialSnapshotIn(BaseModel):
    objects: list[SpatialObject] = Field(default_factory=list, max_length=40)
    place: str | None = Field(default=None, max_length=60)
    lat: float | None = None            # optional GPS → macro-geo binding (smart glasses)
    lon: float | None = None


@router.post("/spatial-snapshot")
def spatial_snapshot(body: SpatialSnapshotIn) -> dict[str, Any]:
    """Spatial Memory Replay (v0): the eye records WHERE things were — distilled geometry only, no
 frame — so the space can be rebuilt later. The browser sends bbox centers; nothing else leaves.

 Objects that carry a signature vector are ALSO cross-checked against past object instances, so a
 returning object is re-recognized (" ") and lands a reunion on the episodic timeline —
 the same-object memory the owner asked for, with zero extra frontend calls."""
    from packages.perception.spatial_memory import record_snapshot

    objs = [{"label": o.label, "x": o.x, "y": o.y, "depth": o.depth, "size": o.size,
             "hue": o.hue, "signature": o.signature} for o in body.objects]
    out = record_snapshot(objs, place=body.place, lat=body.lat, lon=body.lon)
    out["recognized"] = _recognize_objects(objs)
    return out


class GeoAnchorIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float
    lon: float
    address: str | None = Field(default=None, max_length=160)


@router.post("/geo-anchor")
def geo_anchor(body: GeoAnchorIn) -> dict[str, Any]:
    """Mint a symbolic geo node (macro-geo binding): a named place on Earth spatial memories can
    bind to. Symbols only — never imagery; OSM resolution is opt-in, Google scraping refused (ToS)."""
    from packages.perception.geo_anchor import anchor_place

    return anchor_place(body.name, body.lat, body.lon, address=body.address, source="api")


@router.get("/geo-anchors")
def geo_anchors(limit: int = 50) -> dict[str, Any]:
    from packages.perception.geo_anchor import list_anchors

    return {"anchors": list_anchors(limit)}


@router.get("/reconstruction-audit")
def reconstruction_audit() -> dict[str, Any]:
    """The semantic-bottleneck audit: rebuild a known scene from the context schema alone and
    measure what survived. `next_lessons` names the attributes perception must learn to record —
    the measured curriculum (deterministic decoder; generative decoders are barred from truth)."""
    from packages.perception.reconstruction_loss import cycle_audit

    return cycle_audit()


def _recognize_objects(objs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cross-check each signed object against the instance ledger; land a cooldowned reunion event
    for one seen before. Silent on unsigned objects (no signature stream yet → nothing to match)."""
    from packages.perception.object_recognition import recognize_object

    now = time.time()
    seen: list[dict[str, Any]] = []
    for o in objs:
        sig = o.get("signature") or []
        if not sig:
            continue
        r = recognize_object(sig, label=o.get("label"))
        entry = {"label": o.get("label"), "matched": bool(r.get("matched")),
                 "instance_id": r.get("instance_id"), "times_seen": r.get("times_seen")}
        seen.append(entry)
        # a genuine reunion (seen before, recognized again) — cooldowned so a bottle sitting in
        # frame is ONE reunion, not a stream. The episodic lane makes it a real memory.
        if r.get("matched") and int(r.get("times_seen") or 0) >= 2:
            key = f"reunion:{r.get('instance_id')}"
            if now - _last_seen.get(key, 0.0) >= _SEEN_COOLDOWN_S:
                _last_seen[key] = now
                try:
                    from packages.episodic_memory.timeline import record_event

                    record_event("ATANOR", "다시 만남", str(o.get("label") or "물체"),
                                 note=f"재인식 sim={r.get('similarity')} 총 {r.get('times_seen')}회",
                                 source="vision")
                except Exception:
                    pass
    return seen


class ObjectRecognizeIn(BaseModel):
    signature: list[float] = Field(default_factory=list, max_length=128)
    label: str | None = Field(default=None, max_length=40)
    update: bool = True                     # False = probe only (don't mint/absorb) — for queries


@router.post("/object-recognize")
def object_recognize(body: ObjectRecognizeIn) -> dict[str, Any]:
    """The visual signature cells: is this live object one I've seen before? Cross-check its feature
    signature against the instance ledger in real time — conservative threshold, multi-view drift
    adaptation, recency tie-break. Honest: a match is claimed only above the confident threshold."""
    from packages.perception.object_recognition import recognize_object

    return recognize_object(body.signature, label=body.label, update=body.update)


@router.get("/object-instances")
def object_instances() -> dict[str, Any]:
    """How many distinct objects the eye has learned to recognize (read-only, for /ops)."""
    from packages.perception.object_recognition import instance_stats

    return instance_stats()


@router.get("/spatial-snapshots")
def spatial_snapshots(limit: int = 20) -> dict[str, Any]:
    from packages.perception.spatial_memory import list_snapshots

    return {"snapshots": list_snapshots(limit)}


@router.get("/status")
def status() -> dict[str, Any]:
    return _LEDGER.stats()


@router.get("/interests")
def interests() -> dict[str, Any]:
    return {"interests": _LEDGER.interests(), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


@router.post("/clear")
def clear() -> dict[str, Any]:
    try:
        _LEDGER_PATH.unlink()
    except FileNotFoundError:
        pass
    return {"cleared": True}
