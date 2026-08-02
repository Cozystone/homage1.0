from __future__ import annotations

from pathlib import PurePosixPath


def validate_cell_path(path: str, allowed_roots: list[str]) -> bool:
    pure = PurePosixPath(path.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        return False
    normalized = pure.as_posix()
    return any(normalized == root.rstrip("/") or normalized.startswith(root.rstrip("/") + "/") for root in allowed_roots)
