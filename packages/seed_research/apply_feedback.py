from __future__ import annotations

import sys
from pathlib import Path

_INNER_ROOT = Path(__file__).resolve().parent
if str(_INNER_ROOT) not in sys.path:
    sys.path.insert(0, str(_INNER_ROOT))

from seed_research.core import main_feedback


if __name__ == "__main__":
    main_feedback()
