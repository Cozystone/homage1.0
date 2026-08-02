from __future__ import annotations

from pathlib import Path


def test_package_does_not_import_forbidden_runtime_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        "candidate_learning_daemon",
        "packages.cloud_brain",
        "apps.api",
        "apps.web",
        "knowledge_bakery",
        "verified_store_v0",
    ]
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        import_lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        text = "\n".join(import_lines)
        for marker in forbidden:
            assert marker not in text, f"{marker} found in {path}"
