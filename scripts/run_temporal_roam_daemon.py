# -*- coding: utf-8 -*-
"""Detached self-continuing temporal roamer (알아서 계속): each round pulls the curiosity queue,
roams the diverse open web with a real browser, folds observations into the precedence field, and
logs coverage growth. Bounded rounds so it self-terminates cleanly; re-launchable."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.temporal_reasoning.web_explorer import roam_and_learn, load_web_counts  # noqa: E402

LOG = ROOT / "data" / "temporal_reasoning" / "roam_daemon.log"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 6

# curiosity: event pairs whose order is genuinely useful and cross-domain (not exam-copied vocab)
TOPICS = [
    "shipment dispatched arrived delivery timeline",
    "product defect reported recall issued sequence",
    "rocket launch ignition abort landing order",
    "patient symptom onset diagnosis treatment timeline",
    "order placed shipped delivered sequence",
    "incident detected contained resolved timeline",
    "trial started enrolled ended sequence",
    "manufacture inspection shipment recall order",
]


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def coverage() -> int:
    c = load_web_counts()
    return sum(1 for k in c if len(c[k]) >= 2)


def main() -> None:
    log(f"START rounds={ROUNDS} coverage(>=2dom)={coverage()}")
    for i in range(ROUNDS):
        batch = TOPICS[(i * 2) % len(TOPICS): (i * 2) % len(TOPICS) + 2] or TOPICS[:2]
        try:
            s = roam_and_learn(batch, max_pages_per_topic=6)
            log(f"r{i+1} {s} coverage(>=2dom)={coverage()}")
        except Exception as e:
            log(f"r{i+1} ERROR {type(e).__name__}: {e}")
        time.sleep(30)
    log(f"DONE coverage(>=2dom)={coverage()}")


if __name__ == "__main__":
    main()
