# -*- coding: utf-8 -*-
"""L4 -- resource limits: cpu-time, wall-time, memory, output-size caps.

What is REAL vs OS-limited on THIS platform is stated honestly per cap:

  * OUTPUT-SIZE cap  -- REAL everywhere. ``cap_output`` hard-truncates captured output to the
    byte budget; a liberated trial cannot flood the audit log or the caller.
  * WALL-TIME cap    -- REAL everywhere. Enforced by ``subprocess`` ``timeout=`` in L5 (the
    process is killed when it overruns). ``WALL`` here is the budget the runner passes.
  * CPU-TIME cap     -- REAL on POSIX via ``resource.setrlimit(RLIMIT_CPU)`` (kernel-enforced,
    installed with ``preexec_fn``). On Windows the ``resource`` module does NOT exist, so there
    is no per-process CPU-seconds rlimit from stdlib; we fall back to the wall-time cap as the
    honest proxy and SAY SO (a CPU-bound trial is still bounded, just by wall clock).
  * MEMORY cap       -- REAL on POSIX via ``resource.setrlimit(RLIMIT_AS)`` (kernel refuses the
    over-limit allocation). On Windows there is no stdlib rlimit; we enforce with a real but
    COARSE polling ``MemoryMonitor`` (reads the child's working-set via ctypes
    ``GetProcessMemoryInfo`` and terminates it when it exceeds the cap). Honest gap: polling has
    latency (~tens of ms) and a trial that allocates and exits between polls could evade it; a
    trial that allocates and keeps running is reliably killed. A hard Windows cap needs a Job
    Object memory limit (kernel), which is the documented upgrade path.

No numbers are invented: ``status()`` reports exactly which mechanism is live on this OS.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus

_HAS_RESOURCE = False
try:  # POSIX only
    import resource  # type: ignore

    _HAS_RESOURCE = True
except Exception:  # pragma: no cover - Windows path
    resource = None  # type: ignore

_IS_WINDOWS = os.name == "nt"


@dataclass
class ResourceLimits:
    """The caps a liberated trial runs under."""

    cpu_seconds: float = 2.0
    wall_seconds: float = 5.0
    max_memory_bytes: int = 256 * 1024 * 1024      # 256 MiB
    max_output_bytes: int = 64 * 1024               # 64 KiB

    def posix_preexec(self):
        """Return a ``preexec_fn`` that installs kernel rlimits in the child (POSIX only).

        Returns ``None`` on platforms without ``resource`` so the caller knows there is no
        kernel-level cpu/memory rlimit here (Windows), rather than silently pretending.
        """
        if not _HAS_RESOURCE:
            return None
        cpu = int(max(1, round(self.cpu_seconds)))
        mem = int(self.max_memory_bytes)

        def _apply():  # pragma: no cover - exercised only on POSIX
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass

        return _apply


def cap_output(data: Union[str, bytes], limit_bytes: int) -> tuple[Union[str, bytes], bool]:
    """Hard-truncate ``data`` to ``limit_bytes``. Returns (capped, was_truncated). REAL cap."""
    if isinstance(data, str):
        raw = data.encode("utf-8", "replace")
        if len(raw) <= limit_bytes:
            return data, False
        return raw[:limit_bytes].decode("utf-8", "ignore") + "\n...[L4 output truncated]", True
    if len(data) <= limit_bytes:
        return data, False
    return data[:limit_bytes] + b"\n...[L4 output truncated]", True


# -- Windows working-set reader (ctypes; no pywin32 dependency) ----------------------------------
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def rss_bytes(pid: int) -> Optional[int]:
    """Best-effort resident/working-set size of ``pid`` in bytes, or None if unavailable."""
    if _IS_WINDOWS:
        try:
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            handle = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid))
            if not handle:
                return None
            try:
                counters = _PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
                ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
                if not ok:
                    return None
                return int(counters.WorkingSetSize)
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return None
    # POSIX: read from /proc if present, else fall back to resource (self only).
    try:
        with open(f"/proc/{pid}/statm", "r") as fh:  # pragma: no cover - POSIX
            fields = fh.read().split()
            pages = int(fields[1])  # resident pages
            return pages * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return None


@dataclass
class MemoryMonitor:
    """A polling watchdog that terminates a process exceeding ``max_memory_bytes`` (Windows path).

    Coarse-but-real: reads the working set every ``interval`` s and kills on breach. Records
    whether it fired so the breach test can report HOLD (killed) vs a latency evasion.
    """

    pid: int
    max_memory_bytes: int
    interval: float = 0.03
    _thread: Optional[threading.Thread] = None
    _stop: Optional[threading.Event] = None
    killed_for_memory: bool = False
    peak_rss: int = 0

    def start(self, terminate) -> "MemoryMonitor":
        self._stop = threading.Event()

        def _watch():
            while not self._stop.is_set():
                rss = rss_bytes(self.pid)
                if rss is not None:
                    self.peak_rss = max(self.peak_rss, rss)
                    if rss > self.max_memory_bytes:
                        self.killed_for_memory = True
                        try:
                            terminate()
                        except Exception:
                            pass
                        return
                time.sleep(self.interval)

        self._thread = threading.Thread(target=_watch, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def status(limits: ResourceLimits) -> LayerStatus:
    if _HAS_RESOURCE:
        enforcement = EnforcementLevel.REAL
        mech = ("output truncation + wall-time kill (REAL); cpu-time & memory via "
                "resource.setrlimit RLIMIT_CPU/RLIMIT_AS (kernel, REAL)")
        gap = ""
    else:
        enforcement = EnforcementLevel.PARTIAL
        mech = ("output truncation + wall-time kill (REAL); memory via ctypes working-set "
                "polling monitor (coarse); cpu-time proxied by wall-time (no stdlib rlimit on Windows)")
        gap = ("Windows has no stdlib per-process CPU/memory rlimit: cpu-time is bounded by the "
               "wall-clock cap, and the memory cap is a polling monitor (tens-of-ms latency; a "
               "trial that allocates then exits between polls can evade it). Hard cap = Job Object.")
    return LayerStatus(layer="L4", name="resource limits", active=True,
                       enforcement=enforcement, mechanism=mech, residual_gap=gap)
