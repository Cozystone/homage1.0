from __future__ import annotations

import sys
from pathlib import Path


PACKAGES_ROOT = Path(__file__).resolve().parents[2]
for package_root in (PACKAGES_ROOT / "knowledge_bakery", PACKAGES_ROOT / "ontology_forge"):
    package_root_text = str(package_root)
    if package_root_text not in sys.path:
        sys.path.insert(0, package_root_text)
