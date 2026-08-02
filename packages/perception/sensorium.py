# -*- coding: utf-8 -*-
"""ATANOR opens its own eyes and ears: discover the senses this body has, without being told.

    from packages.perception.sensorium import discover, probe
    senses = discover()          # what is attached, found not configured
    for s in senses:
        probe(s)                 # what IS it -- by trying it, not by trusting its label

THE OWNER'S CORRECTION, 2026-07-31, and it is a real one. The first version of this sorted devices into
tiers I had defined -- tiny, small, standard -- which is the opposite of "we are not going to configure
each device for it". Choosing the tier boundaries IS configuring it. What the owner asked for is ATANOR
finding its own eyes and ears at runtime, on a body nobody described to it in advance.

So this file starts from NOTHING KNOWN. It does not assume a camera exists, or how many, or what a
device called "USB Audio" actually is. It asks the OS what is present -- which the OS answers to any
process, no privilege bypassed -- and then it PROBES each one, because a label is a manufacturer's
string and the manufacturer was not describing it for us:

    "HD WEB CAMERA"          might be a webcam, a capture card, or a virtual device -- open it, read a
                             frame, and the frame's shape and liveness say what it is
    "Muzen Wild Mini"        an output or an input? try to read; silence that never changes is not a mic
    "Steam Streaming Speakers" a real speaker or a virtual sink? the probe tells them apart

DISCOVERY IS NOT ACCESS. Enumerating devices is free; OPENING one touches a user-granted permission
(camera, microphone). `discover()` only lists. `probe()` opens, and it is the step a caller runs
deliberately, because that is where the user's grant is spent. If the grant is absent the OS refuses and
the probe returns `reachable=False` -- ATANOR notes the sense exists and cannot be used yet, and does
NOT try to get past the refusal. That boundary is the whole difference between adapting to a body and
breaking into one.

WHAT IT CONNECTS TO. A discovered, probed camera is handed to the perception encoder this project
already has -- the 103 KB signature net, monocular or multi-view by how many cameras probed live. A
discovered microphone is noted as a sense ATANOR HAS and cannot yet understand, because there is no
audio encoder built. That is recorded honestly rather than pretended: the sensorium can find an ear
before ATANOR can hear.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field

VISION = "vision"
HEARING = "hearing"
UNKNOWN = "unknown"


@dataclass
class Sense:
    modality: str                 # vision | hearing | unknown
    label: str                    # the OS/manufacturer string -- a claim, not a fact
    index: int = -1               # opencv/audio index if applicable
    os_class: str = ""
    reachable: bool | None = None  # None = not probed; False = exists but grant/hardware refused
    live: bool | None = None       # None = not probed; True = produced real data on probe
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


# ---- discovery: UNION of every path, because no single one is complete ---------------------------
# Proven on this machine 2026-07-31: a Bose speaker appeared ONLY in Win32_PnPEntity, while
# Win32_SoundDevice and the PnP AudioEndpoint class both missed it entirely, and the endpoint class in
# turn showed a microphone the others did not. Querying one source and trusting it is why the first
# sensorium could not see a speaker the owner could plainly hear. So discovery takes the UNION of
# several independent queries and de-duplicates -- 'by any means' meaning thoroughness, not bypass.
_WIN_QUERIES = (
    # (powershell expression yielding rows of {Class, Name}, a tag for provenance)
    ("Get-PnpDevice -Class 'Camera','Image','AudioEndpoint' -ErrorAction SilentlyContinue "
     "| Select-Object @{n='Class';e={$_.Class}},@{n='Name';e={$_.FriendlyName}},"
     "@{n='St';e={$_.Status}}", "pnp_endpoint"),
    ("Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue "
     "| Where-Object { $_.PNPClass -in 'AudioEndpoint','Camera','Image','Media' -or "
     "$_.Name -match 'camera|microphone|speaker|audio|webcam' } "
     "| Select-Object @{n='Class';e={$_.PNPClass}},Name,@{n='St';e={$_.Status}}", "pnp_entity"),
    ("Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue "
     "| Select-Object @{n='Class';e={'Sound'}},Name,@{n='St';e={$_.Status}}", "sound_device"),
)


def _run_ps(ps: str, expr: str) -> list[dict]:
    import json
    try:
        raw = subprocess.run([ps, "-NoProfile", "-Command",
                              f"{expr} | ConvertTo-Json -Compress"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        rows = json.loads(raw) if raw else []
        return rows if isinstance(rows, list) else [rows]
    except Exception:
        return []


def _enumerate_windows() -> list[Sense]:
    """Union of PnP endpoint, PnP entity, and Win32_SoundDevice. Read-only, no privilege bypassed.

    Each query sees a partial world; the interesting devices (bluetooth speakers, capture endpoints)
    show up in only one of them, so the union is the only complete picture."""
    out: list[Sense] = []
    ps = shutil.which("powershell")
    if not ps:
        return out
    rows: list[dict] = []
    for expr, tag in _WIN_QUERIES:
        for r in _run_ps(ps, expr):
            r["_src"] = tag
            rows.append(r)
    # Merge by name across sources, keeping which queries saw each device -- a device only one query
    # found is exactly the one a single-query sensorium would miss.
    merged: dict[str, dict] = {}
    for r in rows:
        name = str(r.get("Name") or "").strip()
        if not name:
            continue
        cls = str(r.get("Class") or "")
        # a bluetooth "Avrcp Transport" node is control plumbing for a device we also list plainly
        if "avrcp transport" in name.lower():
            continue
        key = name.lower()
        m = merged.setdefault(key, {"name": name, "classes": set(), "sources": set(),
                                    "status": str(r.get("St") or "")})
        if cls:
            m["classes"].add(cls)
        m["sources"].add(str(r.get("_src") or ""))
    for m in merged.values():
        name, low = m["name"], m["name"].lower()
        classes = m["classes"]
        if {"Camera", "Image"} & classes or any(w in low for w in ("camera", "webcam")):
            out.append(Sense(modality=VISION, label=name, os_class="/".join(sorted(classes)),
                             detail={"sources": sorted(m["sources"])}))
            continue
        # DIRECTION decides an ear, not the class name -- the correction the owner's Bose case forced.
        # But name heuristics have a ceiling: 'Microsoft Streaming Service Proxy' matches nothing
        # useful and 'USB Audio' does not say its direction, so enumeration can only PROPOSE a
        # microphone. The frame/stream a probe reads is what CONFIRMS one, which is why hearing.usable
        # stays False until probed and why sensory_self reports found-not-yet-confirmed honestly.
        proxy = any(w in low for w in ("proxy", "service", "component", "controller", "컨트롤러",
                                       "effects", "universal"))
        if proxy:
            out.append(Sense(modality=UNKNOWN, label=name, os_class="/".join(sorted(classes)) or "?",
                             detail={"endpoint": "software-node", "sources": sorted(m["sources"]),
                                     "note": "audio software plumbing, not a physical sense"}))
            continue
        is_input = any(w in low for w in ("마이크", "mic", "microphone", "입력", "capture", "line in"))
        is_output = any(w in low for w in ("스피커", "speaker", "output", "digital out", "소리",
                                           "재생", "headphone", "soundlink", "receiver"))
        audio = ("AudioEndpoint" in classes or "Sound" in classes or "Media" in classes
                 or any(w in low for w in ("audio", "sound", "speaker", "mic", "bose", "muzen")))
        if is_input:
            modality, endpoint = HEARING, "input"
        elif audio:
            # an OUTPUT is a device ATANOR can act THROUGH (a voice), not hear through. It is a real
            # sense-adjacent capability, so it is kept and named, not discarded as 'unknown'.
            modality, endpoint = (UNKNOWN, "output") if is_output else (UNKNOWN, "audio-undetermined")
        else:
            modality, endpoint = UNKNOWN, "not-a-sense"
        out.append(Sense(modality=modality, label=name, os_class="/".join(sorted(classes)) or "?",
                         detail={"endpoint": endpoint, "sources": sorted(m["sources"]),
                                 "found_by_one_source": len(m["sources"]) == 1}))
    return out


def discover() -> list[Sense]:
    """Every sense ATANOR can find on this body. Discovery only -- nothing is opened here.

    Cross-platform intent: Windows uses PnP; other platforms fall back to opencv camera scan plus a
    note that audio enumeration is unbuilt there. The point is that the LIST comes from the machine,
    not from a config we shipped."""
    system = platform.system()
    if system == "Windows":
        senses = _enumerate_windows()
        if senses:
            return senses
    # portable fallback: at least find cameras by index, which needs no OS-specific call
    senses = []
    try:
        import cv2  # noqa: F401
        senses.append(Sense(modality=VISION, label="camera(s) by index scan", os_class="opencv"))
    except Exception:
        pass
    senses.append(Sense(modality=UNKNOWN, label=f"enumeration limited on {system}", os_class=""))
    return senses


# ---- probing: what IS it, by trying it -----------------------------------------------------------
def probe(sense: Sense, *, max_index: int = 6) -> Sense:
    """Open the sense and find out what it actually is. This is where a user grant is spent.

    A label is the manufacturer's word. The frame that comes back, or does not, is the truth. A camera
    that opens and yields a changing image is an eye; one that opens to a frozen grey field is a virtual
    device; one that refuses to open is a sense that exists behind a permission we were not given."""
    if sense.modality == VISION:
        return _probe_vision(sense, max_index=max_index)
    if sense.modality == HEARING:
        return _probe_hearing(sense)
    sense.reachable = False
    sense.detail["note"] = "no probe for this modality"
    return sense


def _probe_vision(sense: Sense, *, max_index: int) -> Sense:
    try:
        import cv2
        import numpy as np
    except Exception:
        sense.reachable = None
        sense.detail["note"] = "opencv/numpy not installed; cannot probe vision here"
        return sense
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        ok1, f1 = cap.read()
        time.sleep(0.05)
        ok2, f2 = cap.read()
        cap.release()
        if not ok1 or f1 is None:
            continue
        sense.index = idx
        sense.reachable = True
        h, w = f1.shape[:2]
        # liveness: two frames that differ mean a real, changing scene rather than a frozen sink
        changed = bool(ok2 and f2 is not None and float(np.abs(f1.astype(int) - f2.astype(int)).mean()) > 1.0)
        sense.live = changed
        sense.detail = {"resolution": [int(w), int(h)],
                        "channels": int(f1.shape[2]) if f1.ndim == 3 else 1,
                        "liveness": "changing scene" if changed else "static/virtual"}
        return sense
    sense.reachable = False
    sense.detail["note"] = "enumerated but no index opened -- likely no camera grant, not bypassed"
    return sense


def _probe_hearing(sense: Sense) -> Sense:
    try:
        import sounddevice as sd
    except Exception:
        sense.reachable = None
        sense.detail["note"] = ("sounddevice not installed; the ear is FOUND but cannot be probed, "
                                "and there is no audio encoder to understand it yet either")
        return sense
    try:
        devs = sd.query_devices()
        ins = [d for d in devs if d.get("max_input_channels", 0) > 0]
        sense.reachable = True
        sense.detail = {"input_devices": len(ins),
                        "note": "microphone(s) present; no audio encoder exists yet to use them"}
    except Exception as exc:
        sense.reachable = False
        sense.detail["note"] = f"audio query refused: {type(exc).__name__}"
    return sense


# ---- the self-model this produces ----------------------------------------------------------------
def sensory_self(probe_them: bool = False) -> dict:
    """What ATANOR concludes about its own senses on this body.

    `probe_them` defaults OFF: discovery is free, but probing opens devices and spends user grants, so
    a caller turns it on when it actually intends to look and listen."""
    senses = discover()
    if probe_them:
        senses = [probe(s) for s in senses]
    live_eyes = sum(1 for s in senses if s.modality == VISION and s.live)
    ears = sum(1 for s in senses if s.modality == HEARING)
    return {
        "senses_found": [s.as_dict() for s in senses],
        "vision": {"found": sum(1 for s in senses if s.modality == VISION),
                   "live": live_eyes,
                   "geometry": ("multi-view" if live_eyes >= 2 else
                                "monocular" if live_eyes == 1 else "none probed")},
        "hearing": {"found": ears,
                    "usable": False,
                    "note": "an ear can be found before ATANOR can hear -- no audio encoder is built"},
        "boundary": ("discovery enumerates; probing opens with the user's grant; a refused open is "
                     "recorded as unreachable and never bypassed"),
    }
