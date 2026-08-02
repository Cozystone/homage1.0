from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MOJIBAKE_FRAGMENTS = ("�", "ATANOR?셲", "?봭", "濡쒖", "釉뚮")


def test_product_and_promotion_ui_labels_do_not_contain_mojibake() -> None:
    paths = [
        REPO_ROOT / "apps/web/app/page.tsx",
        REPO_ROOT / "apps/web/app/AgenticMicroOSPanel.tsx",
        REPO_ROOT / "apps/web/app/ConstructionPromotionPanel.tsx",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for fragment in MOJIBAKE_FRAGMENTS:
            assert fragment not in text, f"{fragment!r} found in {path}"

