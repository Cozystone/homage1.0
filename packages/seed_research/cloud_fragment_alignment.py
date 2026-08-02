from __future__ import annotations

from pathlib import Path
import sys

PACKAGE_ROOT = Path(__file__).resolve().parent / "seed_research"
if str(PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT.parent))

from seed_research.cloud_fragment_alignment import *  # noqa: F401,F403
