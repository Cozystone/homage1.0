#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slow trickle drain — the pace upstream search engines tolerate.

The burst drain suspends SearXNG's engines (brave 429s, ddg CAPTCHA, measured);
one term every couple of minutes stays under every radar and keeps filling the
canonical store overnight. Failures are re-queued a bounded number of rounds so
a term gets retried when engines rotate back up. Logs to data/graph_scale/
trickle_drain.log; stop by deleting data/graph_scale/TRICKLE_RUN.
"""
from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FLAG = REPO / "data" / "graph_scale" / "TRICKLE_RUN"
LOG = REPO / "data" / "graph_scale" / "trickle_drain.log"
QUEUE = REPO / "data" / "graph_scale" / "abstain_queue.jsonl"
INTERVAL = 150          # seconds between terms — engine-suspension-safe
MAX_ROUNDS = 8          # re-queue failed terms this many times, then rest


def log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def requeue(terms: list[str]) -> None:
    with QUEUE.open("a", encoding="utf-8") as f:
        for t in terms:
            f.write(json.dumps({"term": t, "status": "pending", "query": t + "이란?",
                                "ts": datetime.datetime.now().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")


def main() -> int:
    from packages.graph_scale.abstain_feeder import drain

    FLAG.write_text("running", encoding="utf-8")
    log("trickle start")
    failed_rounds: dict[str, int] = {}
    while FLAG.exists():
        got: dict[str, str] = {}

        def capture(msg: str) -> None:
            log(msg)
            m = str(msg).strip()
            if ": no clean definition" in m:
                got[m.split(":", 1)[0].strip()] = "miss"
            elif ": +" in m:
                got[m.split(":", 1)[0].strip()] = "hit"

        counters = drain(limit=1, log=capture)
        if counters.get("terms", 0) == 0:
            log("queue empty — trickle done")
            break
        for term, outcome in got.items():
            if outcome == "miss":
                failed_rounds[term] = failed_rounds.get(term, 0) + 1
                if failed_rounds[term] < MAX_ROUNDS:
                    requeue([term])
                else:
                    log(f"{term}: gave up after {MAX_ROUNDS} rounds (honest gap)")
        time.sleep(INTERVAL)
    log("trickle stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
