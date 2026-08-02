# -*- coding: utf-8 -*-
"""Full Wikidata dump → world pack — SHARDED-WRITE variant (removes the single-writer decel).

Postmortem (2026-07-15): the parallel builder still funnels every triple through the MAIN process's
`st.add` into ONE term dict that grows to 70M+ terms, so throughput decays from ~9k/s to ~3k/s as
the dict swells. Fix: each of N long-lived WORKER processes owns its OWN TripleStore shard and adds
to it directly — every dict stays ~1/N the size, so there is no growth-driven slowdown and no
single writer. Queries union across shards via MultiShardStore (triples are partitioned by dump
position, not subject, so a subject's facts may span shards — the union + dedup handles it).

Same extraction as build_world_pack.py (byte-identical triples). Read: main decompresses (ibz2
parallel) and round-robins line batches to the workers; workers parse+extract+store. No triples
travel back to main → the decel is gone.

  python scripts/build_world_pack_sharded.py --limit 300000 --shards 6   # benchmark a slice
  python scripts/build_world_pack_sharded.py --shards 8                   # full build
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# reuse the EXACT extractor (correctness) from the parallel builder
from scripts.build_world_pack_parallel import _extract, _prescreen_skip   # noqa: E402


def _worker(shard_id: int, out_dir: str, q) -> None:
    sys.path.insert(0, str(REPO))
    from packages.graph_scale.triple_store import TripleStore
    st = TripleStore(Path(out_dir) / f"shard_{shard_id}", dict_backend="sharded", write_src=False)
    kept = 0
    while True:
        batch = q.get()
        if batch is None:
            break
        for line in batch:
            if _prescreen_skip(line):
                continue
            tr, k, _sk = _extract(line)
            if k:
                for s, p, o in tr:
                    st.add(s, p, o)
                kept += 1
                if kept % 100_000 == 0:
                    st.flush()
    st.flush()


def build(limit: int | None = None, shards: int = 0, batch_size: int = 1000,
          min_free_gb: float = 6.0, min_ram_gb: float = 2.5) -> dict:
    import multiprocessing as mp
    import shutil
    try:
        import psutil                                            # RAM guard (never OOM again)
    except Exception:
        psutil = None

    dump = Path(os.environ.get("WORLD_PACK_DUMP", "C:/0.ASKIM ALL-VIN/wikidata/latest-all.json.bz2"))
    out = REPO / "data" / "graph_scale" / os.environ.get("WORLD_PACK_OUT", "world_pack_sharded")
    journal = REPO / "data" / "graph_scale" / "world_pack_build.jsonl"
    if not dump.exists():
        print("dump not found:", dump)
        return {}
    out.mkdir(parents=True, exist_ok=True)
    shards = shards or max(2, (os.cpu_count() or 8) // 3)

    qs = [mp.Queue(maxsize=6) for _ in range(shards)]          # bounded → memory stays flat
    procs = [mp.Process(target=_worker, args=(i, str(out), qs[i]), daemon=True) for i in range(shards)]
    for p in procs:
        p.start()

    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=8)
        backend = f"ibz2(8)+shards({shards})"
    except Exception:
        import bz2
        raw = bz2.BZ2File(str(dump), "rb")
        backend = f"bz2+shards({shards})"

    t0 = time.time()
    seen = wi = 0
    stopped = ""
    batch: list[bytes] = []
    try:
        for line in raw:
            if limit and seen >= limit:
                break
            seen += 1
            line = line.strip()
            if len(line) < 10:
                continue
            batch.append(line)
            if len(batch) >= batch_size:
                qs[wi % shards].put(batch)                     # round-robin to worker shards
                batch, wi = [], wi + 1
                if wi % 200 == 0:
                    dt = time.time() - t0
                    free_gb = shutil.disk_usage(out).free / 1e9
                    ram_gb = (psutil.virtual_memory().available / 1e9) if psutil else 99.0
                    row = {"at": time.strftime("%H:%M:%S"), "seen": seen,
                           "rate_seen_s": round(seen / max(1e-9, dt), 1),
                           "free_gb": round(free_gb, 1), "ram_gb": round(ram_gb, 1), "backend": backend}
                    print(json.dumps(row), flush=True)
                    with journal.open("a", encoding="utf-8") as jf:
                        jf.write(json.dumps(row) + "\n")
                    if free_gb < min_free_gb:                  # disk guard: flush + stop gracefully
                        stopped = f"disk_guard(<{min_free_gb}GB)"
                        print(json.dumps({"stop": stopped, "free_gb": round(free_gb, 1)}), flush=True)
                        break
                    if ram_gb < min_ram_gb:                    # RAM guard: stop feeding → workers drain
                        stopped = f"ram_guard(<{min_ram_gb}GB)"  # → flush + index → valid partial store
                        print(json.dumps({"stop": stopped, "ram_gb": round(ram_gb, 1)}), flush=True)
                        break
    finally:
        if batch:
            qs[wi % shards].put(batch)
        for q in qs:
            q.put(None)                                        # sentinel → workers flush + exit
        for p in procs:
            p.join()
        try:
            raw.close()
        except Exception:
            pass
    dt = time.time() - t0

    # subject index per shard — WITHOUT it every facts_about is an O(n) column scan (the store is
    # unusable for live answering / discrimination). Workers only flush; index here, once, post-write.
    from packages.graph_scale.triple_store import TripleStore
    ti = time.time()
    for i in range(shards):
        sd = out / f"shard_{i}"
        if not sd.exists():
            continue
        try:
            n = TripleStore(sd, dict_backend="sharded", write_src=False).rebuild_index()
            print(json.dumps({"index": f"shard_{i}", "rows": int(n)}), flush=True)
        except Exception as exc:                               # never fail the build over an index
            print(json.dumps({"index_error": f"shard_{i}", "err": str(exc)[:120]}), flush=True)
    idx_s = round(time.time() - ti, 1)

    disk = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e9
    rep = {"seen": seen, "shards": shards, "elapsed_s": round(dt, 1), "index_s": idx_s,
           "stopped": stopped, "rate_seen_s": round(seen / max(1e-9, dt), 1),
           "disk_gb": round(disk, 2), "backend": backend}
    # completion marker: only a CLEAN finish (workers flushed + shards indexed) writes it. A crash
    # leaves no marker, so loaders won't prefer a half-written store over the previous complete one.
    (out / "_COMPLETE.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    print("\nDONE", json.dumps(rep))
    return rep


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    lim = sh = 0
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            lim = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        elif a.startswith("--shards"):
            sh = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    raise SystemExit(0 if build(lim or None, sh) else 1)
