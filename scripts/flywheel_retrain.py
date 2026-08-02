# -*- coding: utf-8 -*-
"""Flywheel retrain tick — closes the self-improvement loop.

Run periodically (scheduler / cron / manual): mines fresh failures from the
conversation log, and when enough NEW labeled gold has accumulated since the
last train, retrains the learned router so real usage keeps making the
understanding layer better. The ATANOR equivalent of a gradient step."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.flywheel import flywheel_stats, mine_failures  # noqa: E402

STATE_PATH = REPO / "data" / "flywheel" / "retrain_state.json"
RETRAIN_THRESHOLD = 25  # new gold rows before a retrain is worth it


def main() -> None:
    mined = mine_failures()
    stats = flywheel_stats()
    print(f"mined: {mined}")
    print(f"stats: {stats}")
    last = 0
    if STATE_PATH.exists():
        try:
            last = json.loads(STATE_PATH.read_text(encoding="utf-8")).get("trained_at_gold", 0)
        except Exception:
            last = 0
    gold_now = stats["failures_mined"] + stats["router_disagreements"]
    if gold_now - last < RETRAIN_THRESHOLD:
        print(f"gold {gold_now} (last train at {last}) — below threshold "
              f"{RETRAIN_THRESHOLD}, no retrain needed yet")
        return
    print(f"gold {gold_now} >= {last}+{RETRAIN_THRESHOLD} — retraining router")
    from scripts.train_router import main as train_main  # noqa: E402

    train_main()
    STATE_PATH.write_text(json.dumps({"trained_at_gold": gold_now}), encoding="utf-8")
    print("retrain complete; state updated")


if __name__ == "__main__":
    main()
