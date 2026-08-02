from __future__ import annotations

import os
import platform
from pathlib import Path


# Keep the original internal AppData namespace for Alpha compatibility.
# ATANOR is the product brand; Homage remains the stable engine/runtime folder.
APP_NAME = "Homage"


def default_app_data_dir() -> Path:
    override = os.getenv("ATANOR_DATA_DIR", os.getenv("HOMAGE_DATA_DIR"))
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system().lower()
    if system == "windows":
        root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_NAME
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / APP_NAME


def configure_desktop_data_dir(data_dir: str | Path | None = None, *, chdir: bool = True) -> Path:
    root = Path(data_dir).expanduser().resolve() if data_dir else default_app_data_dir()
    for child in [
        root,
        root / "data",
        root / "data" / "raw",
        root / "data" / "cleaned",
        root / "data" / "ontology",
        root / "data" / "memory",
        root / "logs",
    ]:
        child.mkdir(parents=True, exist_ok=True)
    os.environ["ATANOR_DATA_DIR"] = str(root)
    os.environ["HOMAGE_DATA_DIR"] = str(root)
    if chdir:
        os.chdir(root)
    return root


def resolve_data_path(*parts: str) -> Path:
    return default_app_data_dir().joinpath(*parts)
