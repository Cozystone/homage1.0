"""Benchmark: does PROCESS-based shard merge beat single-process (GIL-bound) merge?

Threads can't parallelize the merge (it's GIL-bound json/validation — measured).
The honest question for " ": do dedicated WORKER PROCESSES, each owning
disjoint shards, actually scale the merge across cores? This is a standalone
benchmark — it does NOT touch the running server.

Run: python -m packages.brain_link_pool.bench_process_merge
(needs PYTHONPATH including repo root + packages, like the test suite.)
"""

from __future__ import annotations

import datetime
import hashlib
import shutil
import tempfile
import time
from pathlib import Path

from packages.cgsr.cgsr.ingestion.accumulator import VerifiedStore
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence
from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence
from packages.cloud_brain.continuous_learning import ensure_candidate_store_initialized


def _mk(text: str, i: int) -> SourceSentence:
    return SourceSentence(
        text=text, language="en", source_id=f"b-{i}", source_name="bench",
        source_type="local_public_corpus_shard",
        source_hash=hashlib.sha256(f"{text}{i}".encode()).hexdigest()[:16],
        document_id=f"d-{i}", title="b", url="bench", license="CC BY-SA 4.0",
        usage_allowed=True,
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


def _build_decomp_dicts(n: int) -> list[dict]:
    subj = ["A database", "A compiler", "A neuron", "Photosynthesis", "Gravity", "An algorithm",
            "A protein", "A transistor", "A glacier", "A vaccine", "An enzyme", "A planet",
            "A virus", "A polymer", "A galaxy", "A hormone", "A crystal", "A bacterium"]
    pred = ["is an organized collection of structured information",
            "converts source code into machine instructions",
            "transmits electrical signals across synapses",
            "converts light energy into chemical energy",
            "attracts two bodies with mass together",
            "is a finite sequence of defined instructions",
            "is a molecule composed of amino acid chains",
            "amplifies or switches electronic signals"]
    raw = [f"{s} {p}." for s in subj for p in pred]
    out: list[dict] = []
    i = 0
    while len(out) < n:
        s = raw[i % len(raw)]
        ss = _mk(s, i)
        i += 1
        dec = verify_sentence(ss, existing_dedupe_keys=set())
        if getattr(dec, "status", None) != "verified":
            continue
        dr = decompose_sentence(ss, dec, ingest_run_id="bench")
        out.append({"concepts": dr.concepts, "relations": dr.relations,
                    "case_frames": dr.case_frames, "evidence": dr.evidence})
    return out


def _shard_of(d: dict, k: int) -> int:
    ev = d.get("evidence") or {}
    key = str(ev.get("source_hash") or "")
    if not key:
        for c in d.get("concepts") or []:
            key = str(c.get("dedupe_key") or "")
            if key:
                break
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % k


def merge_one_shard(shard_root: str, payloads: list[dict]) -> int:
    """Worker entrypoint (module-level so it is picklable on Windows spawn).
    Builds its shard store ONCE and accumulates its whole load."""
    from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult

    root = Path(shard_root)
    ensure_candidate_store_initialized(root)
    store = VerifiedStore(root)
    drs = [DecompositionResult(concepts=p.get("concepts") or [], relations=p.get("relations") or [],
                               case_frames=p.get("case_frames") or [], evidence=p.get("evidence"))
           for p in payloads]
    res = store.accumulate(drs)
    return int(getattr(res, "concepts_added", 0) or 0)


def _single_process(decomps: list[dict]) -> tuple[float, int]:
    d = Path(tempfile.mkdtemp()) / "s"
    ensure_candidate_store_initialized(d)
    store = VerifiedStore(d)
    from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
    drs = [DecompositionResult(concepts=p.get("concepts") or [], relations=p.get("relations") or [],
                               case_frames=p.get("case_frames") or [], evidence=p.get("evidence"))
           for p in decomps]
    t0 = time.time()
    res = store.accumulate(drs)
    dt = time.time() - t0
    shutil.rmtree(d.parent, ignore_errors=True)
    return dt, int(getattr(res, "concepts_added", 0) or 0)


def _process_sharded(decomps: list[dict], k: int) -> tuple[float, int]:
    from concurrent.futures import ProcessPoolExecutor

    base = Path(tempfile.mkdtemp())
    groups: list[list[dict]] = [[] for _ in range(k)]
    for d in decomps:
        groups[_shard_of(d, k)].append(d)
    roots = [str(base / f"shard_{i:02d}") for i in range(k)]
    # Pool created+warmed OUTSIDE the timed region; time only the parallel merge.
    with ProcessPoolExecutor(max_workers=k) as ex:
        list(ex.map(_noop, range(k)))  # warm workers (pay spawn/import once)
        t0 = time.time()
        added = list(ex.map(merge_one_shard, roots, groups))
        dt = time.time() - t0
    shutil.rmtree(base, ignore_errors=True)
    return dt, sum(added)


def _noop(_x: int) -> int:
    return 0


def main() -> None:
    N = 1500
    print(f"preparing {N} real decompositions...")
    decomps = _build_decomp_dicts(N)
    print(f"prepared {len(decomps)}")

    dt, added = _single_process(decomps)
    base = dt
    print(f"single-process merge        : {dt*1000:7.0f}ms  ({added}c)  -> {len(decomps)/dt:6.0f} decomp/sec")
    for k in (2, 4, 8):
        dt, added = _process_sharded(decomps, k)
        print(f"process-sharded (procs={k})  : {dt*1000:7.0f}ms  ({added}c)  -> {len(decomps)/dt:6.0f} decomp/sec  | speedup x{base/max(dt,1e-9):.2f}")


if __name__ == "__main__":
    main()
