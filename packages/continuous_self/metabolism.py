"""Budget-based metabolism (principle adopted from OpenLife, arXiv 2606.31046 —
no LLM machinery): the self's PACE is set by its real resource wallet, not a
schedule. v0 wallet = the process's own RSS against the watchdog ceiling plus
disk headroom. Two consumers:

  - the continuous learner slows itself down BEFORE the watchdog would have to
    recycle the process (self-regulation instead of external kill), and
  - homeostasis: cortisol's resource_pressure observation becomes a real
    measured number instead of a default 0.
"""
from __future__ import annotations

import os
import shutil
from typing import Any

# must track scripts/engine_watchdog.py rss_limit_mb for the engine service
RSS_CAP_MB = float(os.getenv("ATANOR_RSS_CAP_MB", "12288") or 12288)
DISK_FLOOR_GB = float(os.getenv("ATANOR_DISK_FLOOR_GB", "5") or 5)


def _own_rss_mb() -> float:
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / (1024 * 1024)
    except Exception:
        pass
    try:  # Windows fallback without psutil
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return float(pmc.WorkingSetSize) / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def read_budgets() -> dict[str, float]:
    rss = _own_rss_mb()
    try:
        free_gb = shutil.disk_usage(os.getcwd()).free / (1024 ** 3)
    except Exception:
        free_gb = DISK_FLOOR_GB * 10
    return {"rss_mb": round(rss, 1), "rss_cap_mb": RSS_CAP_MB, "disk_free_gb": round(free_gb, 1)}


def metabolic_state() -> dict[str, Any]:
    """The current metabolic reading — honest degraded: if RSS can't be read
    the pressure is 0 (steady), never invented."""
    budgets = read_budgets()
    mem = min(1.0, max(0.0, budgets["rss_mb"] / max(1.0, budgets["rss_cap_mb"]))) if budgets["rss_mb"] else 0.0
    disk = min(1.0, max(0.0, DISK_FLOOR_GB / max(0.1, budgets["disk_free_gb"])))
    pressure = max(mem, disk)
    if pressure >= 0.85:
        state, pace = "strained", 3.0  # crawl before the watchdog must act
    elif pressure >= 0.65:
        state, pace = "tight", 1.6
    else:
        state, pace = "steady", 1.0
    return {
        "state": state,
        "pressure": round(pressure, 3),
        "pace_multiplier": pace,
        "memory_pressure": round(mem, 3),
        "disk_pressure": round(disk, 3),
        **budgets,
    }
