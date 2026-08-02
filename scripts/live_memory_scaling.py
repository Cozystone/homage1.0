# -*- coding: utf-8 -*-
"""Layer A scaling — the owner asked for human-like memory EFFICIENCY and CAPACITY. 12 facts proved the
property; this measures whether it holds as the store grows 10^2 → 10^5 facts. Honest metrics per scale:
  • recall@1     — does the associative index still put the right fact on top? (the capacity question)
  • latency_ms   — per-query recall time (the efficiency question)
  • bytes/fact   — serialized footprint (vs a human's ~10^9-bit lossy store)
  • build_s      — time to index the whole store

Two regimes, because real recall is not always by a unique token:
  • unique-key   — each fact carries one globally-unique entity token (named-entity recall).
  • shared-key   — the query shares only COMMON tokens with its fact (paraphrase recall). This is where a
    pure lexical inverted index is expected to degrade — an honest wall that motivates embedding retrieval.
No LLM.

  python scripts/live_memory_scaling.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_ATTRS = ["capital", "output", "founder", "mascot", "alloy", "treaty", "engine", "harbor", "glacier", "moon"]
_FILLER = ["report", "system", "record", "value", "peak", "assembly", "core", "city", "north", "lab"]


def _facts(n: int, rng: random.Random):
    """Each fact: '<uniquetoken> ...': a globally-unique entity token + shared filler + a unique value.
    Query-unique probes the unique token; query-shared probes only filler+attr (the hard regime)."""
    out = []
    for i in range(n):
        ent = f"zylquid{i}"                       # globally-unique nonce entity (df==1)
        attr = _ATTRS[i % len(_ATTRS)]
        fill = " ".join(rng.sample(_FILLER, 3))
        val = f"val{i}quon"                        # unique answer token
        fact = f"The {attr} of {ent} is {val}, per the {fill}."
        q_unique = f"What is the {attr} of {ent}?"
        q_shared = f"Tell me the {attr} from the {fill}."   # no unique token → lexical index must guess
        out.append((fact, q_unique, q_shared, i))
    return out


def main():
    from packages.reasoning_vm.live_memory import LiveMemory
    rng = random.Random(0)
    scales = [100, 1000, 10000, 100000]
    rows = []
    for n in scales:
        data = _facts(n, rng)
        lm = LiveMemory(path=REPO / "data" / "graph_scale" / "live_memory" / "_scale_tmp.jsonl")
        lm.items.clear(); lm.inv.clear(); lm.df.clear()      # in-RAM only, no disk churn
        t0 = time.time()
        total_bytes = 0
        for fact, _qu, _qs, _i in data:
            it = lm.remember(fact, source="scale", persist=False)
            total_bytes += len(json.dumps({k: v for k, v in it.items() if k != "_toks"}))
        build_s = time.time() - t0
        # sample 500 probes for recall + latency in each regime
        sample = rng.sample(data, min(500, n))
        hit_u = hit_s = 0
        t1 = time.time()
        for fact, qu, _qs, idx in sample:
            top = lm.recall(qu, k=1)
            hit_u += int(bool(top) and top[0]["text"] == fact)
        lat_u = (time.time() - t1) / len(sample) * 1000
        for fact, _qu, qs, idx in sample:
            top = lm.recall(qs, k=1)
            hit_s += int(bool(top) and top[0]["text"] == fact)
        rows.append({"n": n, "recall@1_unique": round(hit_u / len(sample), 4),
                     "recall@1_shared": round(hit_s / len(sample), 4),
                     "latency_ms_per_query": round(lat_u, 3),
                     "bytes_per_fact": round(total_bytes / n, 1),
                     "build_s": round(build_s, 2), "vocab": len(lm.inv)})
        print(f"n={n:>6} | recall@1 unique {rows[-1]['recall@1_unique']:.3f} "
              f"shared {rows[-1]['recall@1_shared']:.3f} | {rows[-1]['latency_ms_per_query']:.2f} ms/q "
              f"| {rows[-1]['bytes_per_fact']:.0f} B/fact | build {rows[-1]['build_s']:.1f}s", flush=True)

    rep = {"benchmark": "Layer A scaling (lexical inverted index)", "scales": rows,
           "reading": "unique-key recall is the named-entity regime; shared-key is the paraphrase regime "
                      "where a pure lexical index has no discriminating token — the honest wall that "
                      "motivates ACE-embedding (semantic) retrieval as Layer A.2.",
           "human_ref": "human declarative store ~10^9 bits, lossy, ~20W"}
    print("\nRESULT live_memory_scaling", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"live_memory_scaling_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp = REPO / "data" / "graph_scale" / "live_memory" / "_scale_tmp.jsonl"
    if tmp.exists():
        tmp.unlink()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
