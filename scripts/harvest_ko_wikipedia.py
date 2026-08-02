# -*- coding: utf-8 -*-
"""Background harvest of Korean taxonomy from the Korean Wikipedia category tree.

A second, diverse, NOT-rate-limited clean source alongside Wikidata. Writes
incrementally to the candidate ledger.
"""
import sys, time
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")   # Korean cat names safe on cp949 console
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from graph_scale import wikipedia_ko_categories as wc

LOG = Path(__file__).resolve().parents[1] / "data" / "graph_scale" / "harvest_ko_wiki.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


if __name__ == "__main__":
    log("=== wikipedia-ko category harvest: depth 3, cap 60000 ===")
    t0 = time.time()
    res = wc.harvest_ko_categories(max_depth=3, max_edges=60000,
                                   include_pages=True, pace_sec=0.4, log=log)
    log(f"=== done in {int(time.time()-t0)}s -> {res} ===")
