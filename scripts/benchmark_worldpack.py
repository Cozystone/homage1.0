# -*- coding: utf-8 -*-
"""Run the sealed open-book benchmark against a WORLD PACK — READ-ONLY, no live-store swap.

The benchmark harness answers via answer_bridge._store() (the live kg_triples store). This runner
points answer_bridge._ROOT at a world pack and force-reloads it using the documented sig=None
invalidation contract, then runs the existing harness unchanged. The live engine and its kg_triples
files are never touched — a non-destructive report card, exactly the operator-gated swap avoided.

  python scripts/benchmark_worldpack.py                              # world_pack_full, KMMLU, 25/subj
  python scripts/benchmark_worldpack.py --pack=world_pack_partial 10 # a specific pack, 10/subj
  python scripts/benchmark_worldpack.py --bench=mmlu-pro 15          # MMLU-Pro, 15/category
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

pack = "world_pack_full"
passthru: list[str] = []
for a in sys.argv[1:]:
    if a.startswith("--pack="):
        pack = a.split("=", 1)[1]
    else:
        passthru.append(a)

POOL = REPO / "data" / "graph_scale" / pack
if not (POOL / "meta.json").exists():
    print(f"pack not found (build it first): {POOL}")
    raise SystemExit(1)

# point the answer store at the world pack and FORCE a synchronous reload (sig=None is the
# documented force-reload/invalidation contract used by operators after swapping _ROOT).
import packages.graph_scale.answer_bridge as AB  # noqa: E402

AB._ROOT = POOL
AB._STORE["obj"] = None
AB._STORE["sig"] = None
kg = AB._store()
if kg is None:
    print("world pack store failed to load")
    raise SystemExit(1)
meta = json.loads((POOL / "meta.json").read_text(encoding="utf-8"))
print(f"[world-pack read-only] {pack}: {meta.get('count'):,} triples, {meta.get('terms'):,} terms "
      f"— live kg_triples untouched\n")

# run the existing harness main() with the override already in effect (it calls AB._store(),
# which now returns the cached world-pack store). Loaded under a non-__main__ name so its own
# __main__ guard does not double-run; we invoke main() explicitly.
spec = importlib.util.spec_from_file_location("bench_ob", REPO / "scripts" / "benchmark_openbook.py")
mod = importlib.util.module_from_spec(spec)
sys.argv = ["benchmark_openbook.py"] + passthru
spec.loader.exec_module(mod)
raise SystemExit(mod.main())
