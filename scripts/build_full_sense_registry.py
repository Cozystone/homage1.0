# -*- coding: utf-8 -*-
"""Full-coverage sense registry build — RESUMABLE batch over every hub.

Registers every is_a hub (~32k) into the sense registry in chunks; each chunk
persists a new registry version, so killing and rerunning this script loses
nothing (already-registered terms are skipped). Read-only on the store."""
import sys, glob, os, time

sys.path.insert(0, ".")
for d in sorted(glob.glob("packages/*")):
    if os.path.isdir(d):
        sys.path.append(d)

from packages.graph_scale import answer_bridge as ab
from packages.graph_scale.sense_registry import _load, register_terms
from packages.graph_scale.sense_trust_filter import find_hubs

CHUNK = 150

def main():
    st = ab._store()
    done = set((_load().get("terms") or {}).keys())
    hubs = [h for h in find_hubs(st, max_hubs=40000) if h and h not in done]
    print(f"hubs total to register: {len(hubs)} (already done: {len(done)})", flush=True)
    t0 = time.time()
    for i in range(0, len(hubs), CHUNK):
        chunk = hubs[i:i + CHUNK]
        out = register_terms(st, chunk)
        el = time.time() - t0
        rate = (i + len(chunk)) / el if el else 0
        eta = (len(hubs) - i - len(chunk)) / rate / 3600 if rate else 0
        print(f"  {i + len(chunk)}/{len(hubs)} registered (total {out['total']}) "
              f"— {rate:.1f} hubs/s, ETA {eta:.1f}h", flush=True)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
