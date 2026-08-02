from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_package_does_not_import_protected_runtime_paths() -> None:
    forbidden = [
        "candidate_learning_daemon",
        "candidate_live_status",
        "bounded_learning_runner",
        "Local Brain DB",
        "verified_store_v0",
        "apps.api",
        "apps.web",
    ]
    for path in PACKAGE_ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token} unexpectedly referenced by {path}"
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith("from packages.cloud_brain"), f"Cloud Brain import in {path}"
            assert not stripped.startswith("import packages.cloud_brain"), f"Cloud Brain import in {path}"


def test_no_external_llm_service_markers() -> None:
    forbidden = ["openai", "anthropic", "gemini", "external llm api"]
    for path in PACKAGE_ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"{token} unexpectedly referenced by {path}"
