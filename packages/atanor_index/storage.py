"""ATANOR Index storage root resolver — external drive aware ( 2026-07-16: 2TB ).

The index must sit wherever the free space is. Priority:
 1. ATANOR_INDEX_ROOT env override (explicit — always wins).
 2. Largest-free NON-system volume with >= _EXT_MIN_FREE_GB free (the 2TB external when mounted).
 A marker dir `ATANOR_Index/` is created there so the same physical drive is reused on remount.
 3. Fallback: repo `data/atanor_index/` on the system drive (V0 ~10GB fits C:'s free space).

Resolution is cheap (shutil.disk_usage per drive letter) and cached; call `index_root(refresh=True)`
after the drive is plugged in. No write happens on resolve except mkdir of the chosen root.
"""
from __future__ import annotations

import os
import shutil
import string
from pathlib import Path

_EXT_MIN_FREE_GB = 200          # a "big external" — well below 2TB, above any stray USB stick
_CACHE: dict[str, Path] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _system_drive() -> str:
    # Windows: the drive Python/OS lives on (usually C:). POSIX: '/'.
    sysroot = os.environ.get("SystemDrive") or os.path.splitdrive(os.sys.executable)[0] or "C:"
    return sysroot.rstrip("\\/").upper()


def _candidate_volumes() -> list[tuple[float, Path]]:
    """(free_gb, mount_path) for every FIXED/REMOVABLE volume that is NOT the system drive."""
    out: list[tuple[float, Path]] = []
    if os.name == "nt":
        sysd = _system_drive()
        for letter in string.ascii_uppercase:
            drive = f"{letter}:"
            if drive == sysd:
                continue
            root = Path(f"{drive}\\")
            if not root.exists():
                continue
            try:
                free_gb = shutil.disk_usage(root).free / 1e9
            except Exception:
                continue
            out.append((free_gb, root))
    else:
        for mnt in ("/mnt", "/media", "/Volumes", os.path.expanduser("~/mnt")):
            base = Path(mnt)
            if not base.exists():
                continue
            for sub in base.iterdir():
                try:
                    if sub.is_dir():
                        free_gb = shutil.disk_usage(sub).free / 1e9
                        out.append((free_gb, sub))
                except Exception:
                    continue
    out.sort(key=lambda x: -x[0])
    return out


def external_drive() -> Path | None:
    """The big external volume if one is mounted (>= _EXT_MIN_FREE_GB free), else None.
    This is the hook the nightly-arriving 2TB drive lights up — nothing else changes."""
    for free_gb, root in _candidate_volumes():
        if free_gb >= _EXT_MIN_FREE_GB:
            return root
    return None


def index_root(refresh: bool = False) -> Path:
    """Resolve (and mkdir) the ATANOR Index root. Cached; pass refresh=True after plugging a drive."""
    if not refresh and "root" in _CACHE:
        return _CACHE["root"]
    override = os.environ.get("ATANOR_INDEX_ROOT")
    if override:
        root = Path(override)
    else:
        ext = external_drive()
        root = (ext / "ATANOR_Index") if ext is not None else (_repo_root() / "data" / "atanor_index")
    root.mkdir(parents=True, exist_ok=True)
    _CACHE["root"] = root
    return root


def storage_report() -> dict:
    """Human-facing snapshot for the ops surface: where the index lives + what drives are seen."""
    ext = external_drive()
    root = index_root()
    try:
        free_gb = round(shutil.disk_usage(root).free / 1e9, 1)
    except Exception:
        free_gb = None
    return {
        "index_root": str(root),
        "on_external": ext is not None and str(root).startswith(str(ext)),
        "external_drive": str(ext) if ext else None,
        "root_free_gb": free_gb,
        "volumes": [{"mount": str(p), "free_gb": round(g, 1)} for g, p in _candidate_volumes()],
        "min_external_free_gb": _EXT_MIN_FREE_GB,
    }
