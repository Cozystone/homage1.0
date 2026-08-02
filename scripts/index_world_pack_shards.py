# -*- coding: utf-8 -*-
"""Build the subject index for a world-pack store — single TripleStore or a sharded dir.

Without s.perm/s.sorted a store answers facts_about by scanning the whole s-column (O(n)); at
100M+ rows that makes live answering and discrimination unusably slow. The sharded builder now
indexes each shard on completion, but a store built before that fix (or the currently-running build,
which loaded the old code) needs this one-shot pass. Shards are indexed in parallel.

  python scripts/index_world_pack_shards.py world_pack_sharded
  python scripts/index_world_pack_shards.py world_pack_full
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _index_one(store_dir: str) -> dict:
    sys.path.insert(0, str(REPO))
    from packages.graph_scale.triple_store import TripleStore
    t0 = time.time()
    try:
        n = TripleStore(Path(store_dir), dict_backend="sharded", write_src=False).rebuild_index()
        return {"store": Path(store_dir).name, "rows": int(n), "s": round(time.time() - t0, 1)}
    except Exception as exc:
        return {"store": Path(store_dir).name, "error": str(exc)[:140]}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "world_pack_sharded"
    root = REPO / "data" / "graph_scale" / name
    if not root.exists():
        print("not found:", root)
        return 1
    shard_dirs = sorted(root.glob("shard_*"))
    targets = [str(d) for d in shard_dirs] if shard_dirs else [str(root)]
    print(f"indexing {len(targets)} store(s) under {name} …", flush=True)

    if len(targets) > 1:
        import multiprocessing as mp
        with mp.Pool(min(len(targets), 10)) as pool:
            results = pool.map(_index_one, targets)
    else:
        results = [_index_one(t) for t in targets]

    total_rows = sum(r.get("rows", 0) for r in results)
    for r in results:
        print(" ", json.dumps(r, ensure_ascii=False))
    print(f"\nDONE indexed {len(targets)} store(s), {total_rows:,} rows total")
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
