from __future__ import annotations

import sys
from pathlib import Path

_INNER_ROOT = Path(__file__).resolve().parent
if str(_INNER_ROOT) not in sys.path:
    sys.path.insert(0, str(_INNER_ROOT))

from seed_research import *  # noqa: F401,F403,E402
