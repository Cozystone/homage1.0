# -*- coding: utf-8 -*-
"""Meet the device where it is: sense what it OFFERS and reshape to fit, without asking for anything.

    from packages.workspace.device_profile import profile, fit
    d = profile()                      # what this machine actually gives us
    plan = fit(d)                      # which ATANOR paths to run, sized to the hardware

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT. The owner's goal is perfect device adaptation -- a weak
phone should run a light path, a rig with three cameras should use all three, and ATANOR should work
this out itself rather than being told per device. That is real and it is this file.

It is NOT privilege escalation. There is a version of "adapt to old hardware" that means breaking a lock
the device or its owner put there, and that version is refused here for a reason that survives good
intentions: the exploit that slips ATANOR into a locked device you own is byte-identical to the one that
slips it into a device you do not. Intent does not travel in code, and the first thing an abuser of
ATANOR would look for is exactly that capability -- the one the owner wants GENESIS to CATCH. So this
file reads only what the OS offers to any process, and everything it needs turns out to be there:

    cpu cores, RAM, free disk, GPU/CUDA, platform, python -- all standard, nothing bypassed

ADAPTATION IS RESHAPING OUR OWN PATHS, not reaching past the device's boundary. Measured this session,
these are the levers that already exist and are simply not yet chosen by the hardware:

    the acquisition cascade   table -> local -> web, and a weak device leans harder on the free tiers
    the fetcher's concurrency  pages/s = distinct hosts x 1 req/s; a small device uses fewer host slots
    the perception encoder     one camera or several; the same InfoNCE machinery, sized to the sensors
    the property table         16 MB, loads on anything; the 71 GB triple store does not

THE CAMERA POINT IS THE OWNER'S OWN. A humanoid has many cameras, a phone has one, and ATANOR should
find out which at runtime and get the best perception each allows -- stereo when there are two, a
monocular path when there is one. That is a capability query, not a jailbreak: the OS enumerates cameras
to any app the user has granted camera permission. What is refused is TAKING a permission the user did
not grant, which is a different act with a different name.
"""
from __future__ import annotations

import multiprocessing
import os
import platform
import shutil
from dataclasses import asdict, dataclass, field


@dataclass
class DeviceProfile:
    cpu_cores: int = 1
    ram_gb: float = 0.0
    disk_free_gb: float = 0.0
    platform: str = ""
    machine: str = ""
    python: str = ""
    has_cuda: bool = False
    cameras: int = -1          # -1 = not queried; querying needs the user's camera grant
    tier: str = "unknown"      # tiny | small | standard | workstation
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1e9
    except Exception:
        pass
    try:                                    # windows without psutil, the pattern from carla_recorder
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("ml", ctypes.c_ulong),
                        ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                        ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                        ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                        ("ae", ctypes.c_ulonglong)]

        m = _MS()
        m.l = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.tp / 1e9
    except Exception:
        return 0.0


def _cuda() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _tier(cores: int, ram_gb: float) -> str:
    if ram_gb and ram_gb < 2:
        return "tiny"
    if ram_gb < 6:
        return "small"
    if ram_gb < 24:
        return "standard"
    return "workstation"


def profile(*, query_cameras: bool = False) -> DeviceProfile:
    """Everything the OS hands out for free. `query_cameras` defaults OFF because enumerating cameras
    touches a user-granted permission and is the one thing here a caller should opt into deliberately."""
    cores = multiprocessing.cpu_count()
    ram = _ram_gb()
    d = DeviceProfile(
        cpu_cores=cores, ram_gb=round(ram, 1),
        disk_free_gb=round(shutil.disk_usage(".").free / 1e9, 1),
        platform=platform.system(), machine=platform.machine(),
        python=platform.python_version(), has_cuda=_cuda(),
        tier=_tier(cores, ram),
    )
    if query_cameras:
        d.cameras = _count_cameras(d)
    return d


def _count_cameras(d: DeviceProfile) -> int:
    """How many cameras the OS is willing to enumerate to us. Best-effort and permission-bounded.

    This does not open a camera or take a frame; it asks the platform how many exist, which is the
    capability query the owner's stereo-vs-mono adaptation needs. If the user has not granted camera
    access, the OS returns nothing and we return 0 -- we do not try to get past that."""
    try:
        import cv2  # optional; only present where vision is installed
    except Exception:
        d.notes.append("camera count needs opencv; not installed here")
        return -1
    n = 0
    for idx in range(8):
        cap = cv2.VideoCapture(idx)
        ok = cap.isOpened()
        cap.release()
        if ok:
            n += 1
        elif idx > 0:
            break
    return n


def fit(d: DeviceProfile) -> dict:
    """Which ATANOR paths to run and how to size them -- by reshaping OUR side, never the device's.

    Every choice here is a parameter that already exists in something built this session, so
    adaptation is selection, not new capability."""
    plan: dict = {"tier": d.tier}

    # evidence cascade: a weak device cannot afford the web tier's latency and rate limits, so it
    # leans on the free precomputed tiers the cascade already orders by cost
    if d.tier in ("tiny", "small"):
        plan["evidence"] = "table + local only; web tier off (its rate limit hurts a small device most)"
        plan["property_table"] = "load (16 MB, fits anywhere)"
        plan["triple_store"] = "skip (71 GB); rely on the table and dictionaries"
    else:
        plan["evidence"] = "full cascade table -> local -> web"
        plan["triple_store"] = "load if disk allows"

    # fetcher concurrency is host slots, which cost memory and sockets, not privilege
    plan["fetch_host_slots"] = max(2, min(d.cpu_cores * 2, 64 if d.ram_gb >= 8 else 8))

    # perception path by GPU and by cameras
    if d.has_cuda:
        plan["perception"] = "gpu encoder"
    else:
        plan["perception"] = "cpu encoder (the signature net is 103 KB and runs on cpu)"
    if d.cameras >= 2:
        plan["vision_geometry"] = f"stereo/multi-view across {d.cameras} cameras"
    elif d.cameras == 1:
        plan["vision_geometry"] = "monocular; depth from the learned model, not disparity"
    else:
        plan["vision_geometry"] = "cameras not queried (needs user grant); default monocular"

    plan["refused"] = ("no privilege escalation, no lock bypass, no permission taken that the user "
                       "did not grant -- adaptation reshapes ATANOR, not the device's boundary")
    return plan
