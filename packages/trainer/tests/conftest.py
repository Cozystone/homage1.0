from __future__ import annotations

import sys
from pathlib import Path


PACKAGES_ROOT = Path(__file__).resolve().parents[2]
for package_root in (PACKAGES_ROOT / "trainer", PACKAGES_ROOT / "model"):
    package_root_text = str(package_root)
    if package_root_text not in sys.path:
        sys.path.insert(0, package_root_text)
