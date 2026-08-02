from __future__ import annotations

from pathlib import Path


def detect_license(repo_path: Path) -> dict[str, object]:
    license_path = repo_path / "LICENSE"
    if not license_path.exists():
        return {"license_file_present": False, "license_detected": "missing", "mit_compatible": False}
    text = license_path.read_text(encoding="utf-8", errors="ignore").lower()
    detected = "MIT" if "mit license" in text and "permission is hereby granted" in text else "unknown"
    return {
        "license_file_present": True,
        "license_detected": detected,
        "mit_compatible": detected == "MIT",
    }
