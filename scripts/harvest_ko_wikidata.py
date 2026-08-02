# -*- coding: utf-8 -*-
"""Paced background harvest of Korean taxonomy from Wikidata (is_a backbone).

Respects WDQS ~1 req/min. Writes incrementally to the candidate ledger, so a
partial run is still useful. Focused on P279 (subclass) + P31 (instance) — the
is_a backbone that fixes Korean geometry (→, →).
"""
import sys, time
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from graph_scale import wikidata_ko as w

LOG = Path(__file__).resolve().parents[1] / "data" / "graph_scale" / "harvest_ko.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


if __name__ == "__main__":
    log("=== harvest start: P279 + P31, batch 2000, pace 62s, cap 30000/rel ===")
    t0 = time.time()
    res = w.harvest_ko(relations=("P279", "P31"), batch=2000, max_per_rel=30000,
                       pace_sec=62.0, log=log)
    log(f"=== done in {int(time.time()-t0)}s -> {res} ===")
