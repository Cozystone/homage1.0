from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = PACKAGE_ROOT.parent
for path in [PACKAGE_ROOT, PACKAGES_ROOT / "knowledge_bakery"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
