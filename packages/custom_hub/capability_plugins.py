# -*- coding: utf-8 -*-
"""Custom Hub — capability plugins that keep heavy abilities OUT of the lean base install.

The base ATANOR must run on a low-spec laptop, so a ~1GB dependency like face recognition
(DeepFace/tensorflow) can never sit in the core download. Instead the Custom Hub lists such
abilities as PLUGINS with their real disk cost and live install status; the user adds only what
they have the disk — and the reason — for.

Zones (owner 2026-07-11):
  * graph  — knowledge cartridges (the existing Graph Hub marketplace, unchanged)
  * device — perception / hardware abilities: face recognition, smart-glasses object detection,
             humanoid rig. Heavy deps → plugins, not base.
  * ato    — the character / avatar layer (particle Ato; optional cloud generators)

HONESTY: a plugin's status is MEASURED (its real dependency imports, or its files exist), never
assumed. Nothing here installs anything — it reports the truth and hands the operator the exact
command, so a pip triggered from a web request never runs unsupervised. Base-native abilities
(browser WASM object detection, the numpy particle Ato) report disk_mb 0 and status 'base'.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]


def _mod(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _weights_present() -> bool:
    try:
        return (Path.home() / ".deepface" / "weights" / "facenet_weights.h5").exists()
    except Exception:
        return False


def _splatra_src() -> bool:
    """SPLATRA (atanor-hologram-core) is a sibling repo whose numpy-only core is usable the
    moment its source tree is present — the heavy photoreal tiers ([gpu]/[gen]) are separate."""
    try:
        return (_REPO.parent / "26.SPLATRA" / "src" / "atanor_core").exists()
    except Exception:
        return False


def _alphaframer_src() -> bool:
    """AlphaFramer is the OPEN spatial-perception protocol — a sibling repo (github Cozystone/
    AlphaFramer) backed out of this monorepo. Present the standalone form when its tree is here;
    the perception it exposes is base-native to ATANOR either way (the ATANOR core is NOT in it)."""
    try:
        return (_REPO.parent / "AlphaFramer" / "alphaframer" / "__init__.py").exists()
    except Exception:
        return False


# Each plugin declares its ZONE, real disk footprint, what proves it installed (a probe), and the
# exact operator command to add it. `status` is filled at read time — never hard-coded.
# Within `device`, perception splits by the SENSE it uses (owner 2026-07-11): `self` = ATANOR
# reading its own inner state; `camera` = reading the outside world through a camera / smart
# glasses (face, pose, objects, depth); `io` = motor + voice (not perception, but device-side).
_PLUGINS: list[dict[str, Any]] = [
    {
        "id": "self_perception", "zone": "device", "group": "self", "name": "셀프 인식 (자기 상태)",
        "name_en": "Self-Perception (Own State)",
        "desc": "ATANOR가 자기 내부 상태 — 호르몬·기분·각성·자기모델 — 를 스스로 읽는 지각. 카메라 없이도 늘 켜져 있는 기본 감각.",
        "desc_en": "ATANOR reading its own inner state — hormones, mood, arousal, self-model. Always-on, no camera.",
        "disk_mb": 0, "install_hint": None,
        "probe": lambda: True,
        "provides": ["/api/continuous-self", "self-state"],
    },
    {
        "id": "face_recognition", "zone": "device", "group": "camera", "name": "얼굴 인식",
        "name_en": "Face Recognition",
        "desc": "카메라로 사람을 알아보고 상태를 읽습니다. 모르는 얼굴은 지어내지 않고 물어볼 여지를 남깁니다.",
        "desc_en": "Recognizes people and reads state from the camera; an unknown face stays an honest gap.",
        "disk_mb": 1000, "install_hint": "pip install deepface tf-keras",
        "probe": lambda: _mod("deepface") and _mod("tensorflow"),
        "extra": lambda: {"weights_ready": _weights_present()},
        "provides": ["/api/perception/face-ingest", "/perception"],
    },
    {
        "id": "pose_recognition", "zone": "device", "group": "camera", "name": "포즈 · 자세 인식",
        "name_en": "Pose / Posture Recognition",
        "desc": "카메라로 사람의 자세와 제스처를 읽습니다(앉음·서있음·팔 듦 등). 브라우저 WASM(MediaPipe Pose)로 돌아 "
                "추가 설치·서버 용량이 없고, 프레임 대신 정제된 자세만 남깁니다.",
        "desc_en": "Reads posture and gestures from the camera (sitting/standing/arms-raised). Browser WASM "
                   "(MediaPipe Pose) — zero server disk, only distilled posture leaves the page.",
        "disk_mb": 0, "install_hint": None,
        "probe": lambda: True,          # in-browser MediaPipe Pose: always available, zero server disk
        "provides": ["/api/perception/pose-ingest", "/perception"],
    },
    {
        "id": "object_detection", "zone": "device", "group": "camera", "name": "객체 인식",
        "name_en": "Object Detection",
        "desc": "카메라 속 사물을 기기 안에서 감지합니다. 브라우저 WASM로 도니 추가 설치가 필요 없어요.",
        "desc_en": "Detects objects on-device via browser WASM — no extra download.",
        "disk_mb": 0, "install_hint": None,
        "probe": lambda: True,          # in-browser MediaPipe: always available, zero server disk
        "provides": ["/api/perception/visual-ingest", "/perception"],
    },
    {
        "id": "alphaframer", "zone": "device", "group": "camera", "name": "AlphaFramer (공간 지각 프로토콜)",
        "name_en": "AlphaFramer (Spatial Perception Protocol)",
        "desc": "프레임을 저장하지 않는 공간 지각 프로토콜 — 물체 재인식(시각 서명), 공간 기억(정제 기하만), "
                "세맨틱 보틀넥 감사(복원으로 이해를 검증). 오픈소스, 두뇌(추론 코어)는 포함하지 않음.",
        "desc_en": "The no-frame spatial-perception protocol — object re-recognition (visual signatures), "
                   "spatial memory (distilled geometry only), semantic-bottleneck audit. Open-source; the "
                   "reasoning core is NOT included.",
        "disk_mb": 5, "install_hint": "git clone github.com/Cozystone/AlphaFramer (형제 레포) — 오픈 프로토콜",
        "probe": _alphaframer_src,
        "provides": ["/api/perception/spatial-snapshot", "/api/perception/object-recognize",
                     "/api/perception/reconstruction-audit", "alphaframer (pip)"],
    },
    {
        "id": "depth_perception", "zone": "device", "group": "camera", "name": "깊이 인식 (공간·AR)",
        "name_en": "Depth Perception (Spatial / AR)",
        "desc": "단안 카메라로 장면의 깊이를 읽습니다. 스마트글래스 공간 이해와 '저 물병 집어줘' 같은 3D 지시의 밑바탕.",
        "desc_en": "Monocular scene depth — the base for smart-glasses spatial tasks and 3D instructions.",
        "disk_mb": 800, "install_hint": "pip install transformers torch  (Depth-Anything V2)",
        "probe": lambda: _mod("depth_anything_v2") or _mod("midas"),
        "provides": ["/api/perception/depth", "/perception"],
    },
    {
        "id": "voice_io", "zone": "device", "group": "io", "name": "음성 입출력 (듣기·말하기)",
        "name_en": "Voice I/O (Listen / Speak)",
        "desc": "말로 묻고 목소리로 답합니다. 로컬 STT(Whisper) + TTS — 마이크·스피커만 있으면 대화가 손을 떠납니다.",
        "desc_en": "Ask by voice, hear the answer — local Whisper STT + TTS, no cloud.",
        "disk_mb": 1500, "install_hint": "pip install faster-whisper TTS",
        "probe": lambda: _mod("faster_whisper") or _mod("whisper"),
        "provides": ["/api/voice", "STT + TTS"],
    },
    {
        "id": "humanoid_rig", "zone": "device", "group": "io", "name": "휴머노이드 리그 (동작)",
        "name_en": "Humanoid Rig (Motion)",
        "desc": "생성된 몸에 뼈대를 세우고 움직이게 합니다. 학습형 리그 예측기(torch) 기반.",
        "desc_en": "Rigs a generated body and drives it — learned rig predictor (torch).",
        "disk_mb": 350, "install_hint": "pip install torch",
        "probe": lambda: _mod("torch"),
        "provides": ["SPLATRA /v1/rig_animate"],
    },
    {
        "id": "particle_ato", "zone": "ato", "name": "파티클 아토 (기본 캐릭터)",
        "name_en": "Particle Ato (Base Character)",
        "desc": "ATANOR의 얼굴 — 순수 numpy 파티클 아바타. 기본 탑재, 용량 0.",
        "desc_en": "ATANOR's face — a pure-numpy particle avatar. Base, zero disk.",
        "disk_mb": 0, "install_hint": None,
        "probe": lambda: True,
        "provides": ["SplatraField", "avatar/ato"],
    },
    {
        "id": "splatra_3d", "zone": "ato", "name": "SPLATRA 3D 홀로그램 엔진",
        "name_en": "SPLATRA 3D Hologram Engine",
        "desc": "텍스트·기하를 3D 가우시안 파티클 홀로그램으로 만드는 자체 엔진. 코어는 순수 numpy라 가볍고, "
                "사실적 렌더는 아래 '사실적 3D'로, 실시간 GPU 스플랫은 [gpu] 티어로 확장합니다.",
        "desc_en": "Own engine turning text/geometry into 3D Gaussian particle holograms. Pure-numpy "
                   "core (light); photoreal via 'Realistic 3D', real-time GPU splatting via [gpu].",
        "disk_mb": 5, "install_hint": "pip install -e 26.SPLATRA  (numpy 코어; 실시간/사실적은 [gpu]/[gen] extra)",
        "probe": _splatra_src,
        "provides": ["SPLATRA :8010 /v1/generate", "3D Gaussian hologram"],
    },
    {
        "id": "realistic_3d", "zone": "ato", "name": "사실적 3D 생성",
        "name_en": "Realistic 3D Generation",
        "desc": "SPLATRA의 사실적 렌더 티어 — 텍스트/이미지를 실사 같은 3D 입자 객체로(SD/TripoSR 경로, 무겁고 선택).",
        "desc_en": "SPLATRA's photoreal tier — text/image into lifelike 3D particle objects (SD/TripoSR, heavy, optional).",
        "disk_mb": 6000, "install_hint": "pip install -e 26.SPLATRA[gen]  (SD/TripoSR, HF cache)",
        "probe": lambda: _mod("diffusers") and _mod("torch"),
        "provides": ["SPLATRA :8010 [gen]"],
    },
    {
        "id": "higgsfield_avatar", "zone": "ato", "name": "Higgsfield 아바타 (클라우드)",
        "name_en": "Higgsfield Avatar (Cloud)",
        "desc": "클라우드 캐릭터/영상 생성. 로컬 용량 0(외부 API·키 필요) — No-LLM 코어 밖의 선택 확장.",
        "desc_en": "Cloud character/video generation. Zero local disk (external API + key) — an "
                   "optional extension OUTSIDE the No-LLM core.",
        "disk_mb": 0, "install_hint": "requires HIGGSFIELD_API_KEY (cloud, opt-in)",
        "probe": lambda: bool(__import__("os").environ.get("HIGGSFIELD_API_KEY")),
        "provides": ["(cloud) Higgsfield API"],
    },
]


def disk_free_mb() -> int:
    try:
        return int(shutil.disk_usage(_REPO).free / (1024 * 1024))
    except Exception:
        return 0


def plugin_status() -> dict[str, Any]:
    """The Custom Hub's device/ato plugins with LIVE status + real disk cost, grouped by zone."""
    free = disk_free_mb()
    out: list[dict[str, Any]] = []
    for p in _PLUGINS:
        try:
            installed = bool(p["probe"]())
        except Exception:
            installed = False
        base = p["disk_mb"] == 0 and installed
        entry = {
            "id": p["id"], "zone": p["zone"], "group": p.get("group"),
            "name": p["name"], "name_en": p["name_en"],
            "desc": p["desc"], "desc_en": p["desc_en"], "disk_mb": p["disk_mb"],
            "install_hint": p["install_hint"], "provides": p["provides"],
            "status": "base" if base else ("installed" if installed else "available"),
            "fits_disk": p["disk_mb"] <= free,
        }
        if "extra" in p:
            try:
                entry.update(p["extra"]())
            except Exception:
                pass
        out.append(entry)
    return {
        "zones": ["graph", "device", "ato"],
        "disk_free_mb": free,
        "plugins": out,
    }
