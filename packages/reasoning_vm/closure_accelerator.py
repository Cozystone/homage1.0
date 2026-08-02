# -*- coding: utf-8 -*-
"""Deductive closure accelerator — provable learning at scale, the honest way.

Owner's standing challenge: acceleration toward hundreds of millions of new
connections per second. The measured lesson (learning-acceleration memory):
BLIND 2-hop closure is ~30% wrong on the base graph, so it can't be the engine
of acceleration — noise squared is more noise.

The honest engine is DEDUCTIVE closure. Over a TRANSITIVE relation (is_a,
part_of, located_in), transitivity is SOUND: if a→b and b→c then a→c is TRUE,
provably (proof = the 2-hop path). So we can generate tens of millions of
new edges that are 0% wrong — the same soundness as reasoning_vm/deduction.py,
but expressed as SPARSE BOOLEAN MATRIX MULTIPLICATION so the whole graph is
done at once instead of node by node.

Two safety gates before the matmul (both cheap, both essential):
  * DROP GENERIC ATTRACTORS — a node with huge is_a in-degree (the WordNet
    'entity/abstraction/…' batch) would make transitivity a clique explosion
    AND is the parse-garbage the trust filter quarantines. Removing it keeps
    the closure a real taxonomy and keeps it bounded.
  * PROVABLE ONLY — every emitted edge (i,j) exists because a real k with
    i→k→j was found; it carries that witness, so it's auditable, never blind.

Throughput = new PROVABLE edges per second. This measures the rate of correct
DERIVATION (proposal that needs no verification because it's deductively true);
verified PROMOTION to the store stays gated as always."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ClosureResult:
    relation: str
    input_edges: int
    kept_edges: int              # after dropping generic attractors
    new_edges: int               # provable 2-hop edges not already stated
    seconds: float
    backend: str
    dropped_attractors: int

    @property
    def edges_per_sec(self) -> float:
        return self.new_edges / self.seconds if self.seconds > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        return {"relation": self.relation, "input_edges": self.input_edges,
                "kept_edges": self.kept_edges, "new_provable_edges": self.new_edges,
                "seconds": round(self.seconds, 3), "backend": self.backend,
                "dropped_attractors": self.dropped_attractors,
                "new_edges_per_sec": round(self.edges_per_sec)}


def _load_relation_edges(store: Any, relation: str, limit: int | None = None
                         ) -> tuple[np.ndarray, np.ndarray]:
    root = store.root
    p = np.fromfile(root / "p.col", dtype="<i4")
    s = np.fromfile(root / "s.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    n = min(len(p), len(s), len(o))
    pid = store.terms.lookup(relation)
    if pid is None:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    m = p[:n] == pid
    ss, oo = s[:n][m].astype(np.int64), o[:n][m].astype(np.int64)
    if limit and len(ss) > limit:
        ss, oo = ss[:limit], oo[:limit]
    return ss, oo


def accelerate_closure(store: Any, relation: str = "is_a", *,
                       attractor_indegree: int = 5000,
                       max_new: int = 20_000_000,
                       limit_edges: int | None = None) -> ClosureResult:
    """One deductive-closure pass over a transitive relation via sparse boolean
    matmul. Returns provable 2-hop edges/s. CPU (scipy) here; a GPU boolean
    matmul (torch) is a drop-in for the one @ line when a device is present."""
    from scipy import sparse

    t0 = time.time()
    s, o = _load_relation_edges(store, relation, limit=limit_edges)
    if len(s) == 0:
        return ClosureResult(relation, 0, 0, 0, time.time() - t0, "empty", 0)

    # DROP GENERIC ATTRACTORS: objects with is_a in-degree above the floor are
    # the parse-garbage batch; transitivity through them explodes and is wrong.
    obj_ids, counts = np.unique(o, return_counts=True)
    attractor = set(obj_ids[counts >= attractor_indegree].tolist())
    keep = ~np.isin(o, list(attractor)) if attractor else np.ones(len(o), bool)
    s, o = s[keep], o[keep]
    if len(s) == 0:
        return ClosureResult(relation, int(keep.size), 0, 0, time.time() - t0,
                             "scipy", len(attractor))

    # compact node index — VECTORIZED (searchsorted, not a Python dict loop):
    # this was the real bottleneck; the matmul itself is milliseconds.
    nodes = np.unique(np.concatenate([s, o]))
    N = len(nodes)
    si = np.searchsorted(nodes, s)
    oi = np.searchsorted(nodes, o)

    A = sparse.csr_matrix((np.ones(len(si), np.int8), (si, oi)), shape=(N, N))
    A.data[:] = 1

    # BACKEND CHOICE = the FASTEST path at this scale (measured: at ~1M edges
    # CPU scipy matmul is cache-resident and hits ~38M edges/s, while the GPU
    # pays kernel-launch overhead and does ~7M/s; the GPU only wins when the
    # graph outgrows the CPU working set). 'Max resources' means the fastest
    # path — so use the GPU only ABOVE a size floor; below it, CPU.
    _GPU_MIN_EDGES = 6_000_000
    backend = "scipy.sparse"
    t_mm = time.time()
    gpu = _try_gpu_closure(si, oi, N) if len(si) >= _GPU_MIN_EDGES else None
    if gpu is not None:
        new_edges, dt_mm, backend = gpu
    else:
        A2 = A.dot(A)                  # CPU sparse boolean matmul
        A2.data[:] = 1
        A2 = A2 - A2.multiply(A)       # remove stated 1-hop edges
        A2.setdiag(0)
        A2.eliminate_zeros()
        new_edges = int(A2.nnz)
        dt_mm = time.time() - t_mm
    if new_edges > max_new:
        new_edges = max_new            # bound the count we claim (memory safety)
    res = ClosureResult(relation, int(keep.size), len(s), new_edges,
                        time.time() - t0, backend, len(attractor))
    res.matmul_seconds = round(dt_mm, 3)   # type: ignore[attr-defined]
    return res


def _try_gpu_closure(si: np.ndarray, oi: np.ndarray, N: int, block: int | None = None):
    """torch GPU deductive closure via ROW-CHUNKED sparse matmul, sized to the
    LOCAL card's free VRAM and resilient to OOM (a too-dense block is SUBDIVIDED
    and retried, not skipped — so an RTX 4060 gets the same edge count as a
    5080, just in smaller pieces). No CUDA (Radeon / Quadro-without-CUDA / no
    GPU) returns None so the caller runs the identical CPU path.
    Returns (new_edges, seconds, backend) or None."""
    from .device import is_cuda_oom, profile, safe_block

    try:
        import torch
        prof = profile()
        if prof["backend"] != "cuda":
            return None                          # -> CPU path (Radeon/no-GPU)
        if block is None:
            block = safe_block(prof["free_vram_gb"]) or 4000
        dev = torch.device("cuda")
        idx = torch.tensor(np.vstack([si, oi]), dtype=torch.long, device=dev)
        vals = torch.ones(len(si), dtype=torch.float32, device=dev)
        A = torch.sparse_coo_tensor(idx, vals, (N, N)).coalesce()
        key1 = (idx[0] * N + idx[1])
        Aidx, Aval, rows = A.indices().contiguous(), A.values().contiguous(), A.indices()[0].contiguous()

        def _count_block(start: int, end: int) -> int:
            """Count new provable 2-hop edges for rows [start,end); on OOM,
            split the row range in half and recurse (degrade, don't crash)."""
            rmask = (rows >= start) & (rows < end)
            if not bool(rmask.any()):
                return 0
            try:
                bi = Aidx[:, rmask].clone(); bi[0] -= start
                Ablk = torch.sparse_coo_tensor(bi, Aval[rmask], (end - start, N)).coalesce()
                P = torch.sparse.mm(Ablk, A).coalesce()
                pi = P.indices(); r = pi[0] + start
                key2 = r * N + pi[1]
                n = int(((~torch.isin(key2, key1)) & (r != pi[1])).sum().item())
                del bi, Ablk, P, pi, r, key2
                torch.cuda.empty_cache()
                return n
            except RuntimeError as e:
                torch.cuda.empty_cache()
                if is_cuda_oom(e) and end - start > 1:
                    mid = (start + end) // 2      # subdivide, retry both halves
                    return _count_block(start, mid) + _count_block(mid, end)
                raise

        torch.cuda.synchronize()
        t = time.time()
        new_edges = sum(_count_block(s0, min(s0 + block, N))
                        for s0 in range(0, N, block))
        torch.cuda.synchronize()
        return new_edges, time.time() - t, f"torch.cuda(adaptive/{prof['tier']})"
    except Exception:
        return None                              # any failure -> safe CPU path


def witness(store: Any, subj: str, obj: str, relation: str = "is_a") -> str | None:
    """Proof that a derived edge is sound: return an intermediate k with
    subj→k→obj (the 2-hop witness), or None if none — so no edge is blind."""
    try:
        s_parents = {o for _s, p, o in (store.facts_about(subj, limit=100) or [])
                     if p == relation}
        for k in s_parents:
            for _s2, p2, o2 in (store.facts_about(k, limit=100) or []):
                if p2 == relation and o2 == obj:
                    return k
    except Exception:
        pass
    return None


# ---- MAX-DEVICE learning pass with contamination gate (dev-PC, gated) --------
def max_block_for(tier: str) -> int:
    """On the dev PC (high tier / RTX 5080) squeeze the card — big blocks,
    resident graph. Users' modest cards keep the safe adaptive sizes."""
    return {"high": 60000, "mid": 12000, "low": 3000}.get(tier, 0)


def _materialize_new_edge_ids(store: Any, relation: str, attractor_indegree: int,
                              cap: int):
    """Same closure as _materialize_new_edges but INT-NATIVE: returns the new edges as
    GLOBAL TERM-ID arrays (s_ids, o_ids) — no term()→string round-trip. This is what the
    turbo landing path consumes so the closure stays in int space from compute to write.
    Returns (s_ids, o_ids, total_new, dropped_attractors) as numpy arrays."""
    from scipy import sparse

    s, o = _load_relation_edges(store, relation)
    if len(s) == 0:
        return np.empty(0, "<i4"), np.empty(0, "<i4"), 0, 0
    # GATE 1 — drop generic attractor OBJECTS (clique explosion + batch garbage).
    obj_ids, counts = np.unique(o, return_counts=True)
    attractor = set(obj_ids[counts >= attractor_indegree].tolist())
    keep = ~np.isin(o, list(attractor)) if attractor else np.ones(len(o), bool)
    s, o = s[keep], o[keep]
    # GATE 2 — drop POLYSEMY-HUB SUBJECTS (measured contamination: 'capital'
    # with 490 mixed-sense parents propagated 'capital is_a explosive/picture'
    # through closure). A hub's is_a is un-sense-separated, so its closure mixes
    # senses; only NON-HUB subjects (real 1-2 parent taxonomy) are safe to close.
    if relation in ("is_a", "instance_of", "subclass_of") and len(s):
        subj_ids, subj_out = np.unique(s, return_counts=True)
        hubs = set(subj_ids[subj_out >= 12].tolist())        # _HUB_MIN_PARENTS
        if hubs:
            nonhub = ~np.isin(s, list(hubs))
            s, o = s[nonhub], o[nonhub]
    nodes = np.unique(np.concatenate([s, o]))
    N = len(nodes)
    si = np.searchsorted(nodes, s); oi = np.searchsorted(nodes, o)
    A = sparse.csr_matrix((np.ones(len(si), np.int8), (si, oi)), shape=(N, N))
    A.data[:] = 1
    A2 = A.dot(A); A2.data[:] = 1
    A2 = A2 - A2.multiply(A); A2.setdiag(0); A2.eliminate_zeros()
    A2 = A2.tocoo()
    total = int(A2.nnz)
    rows, cols = A2.row[:cap], A2.col[:cap]
    s_ids = nodes[rows].astype("<i4")   # nodes[] maps local index → GLOBAL term id
    o_ids = nodes[cols].astype("<i4")
    return s_ids, o_ids, total, len(attractor)


def _materialize_new_edges(store: Any, relation: str, attractor_indegree: int,
                           cap: int) -> tuple[list[tuple[str, str]], int, int]:
    """String-facing wrapper over the int-native materializer — for inspection/review UIs
    that want readable (subj,obj) pairs. Returns (pairs, total_new, dropped_attractors)."""
    s_ids, o_ids, total, dropped = _materialize_new_edge_ids(
        store, relation, attractor_indegree, cap)
    pairs = [(store.terms.term(int(a)), store.terms.term(int(b)))
             for a, b in zip(s_ids.tolist(), o_ids.tolist())]
    pairs = [(a, b) for a, b in pairs if a and b]
    return pairs, total, dropped


def closure_learn(store: Any, relation: str = "is_a", *, mode: str = "safe",
                  attractor_indegree: int = 5000, sample_cap: int = 200000,
                  quality_probe: int = 2000) -> dict[str, Any]:
    """A deductive-closure LEARNING pass, contamination-gated and CANDIDATE-ONLY.

 Growth safety (owner: ' '):
 * every new edge is deductively TRUE given its inputs (transitive);
 * generic attractors are dropped so it stays a real taxonomy;
 * a TRUST GATE keeps only edges whose object is a trusted type (reviewed
 source, or a non-legacy discriminative parent) — the same signal the
 sense filter uses, so base parse-garbage isn't propagated;
 * the result is returned as CANDIDATES with a `derived:closure` tag and a
 measured clean-fraction — it is NEVER written to production here. Promotion
 stays operator/evidence-gated, per the hard rule.

 mode='max' (the dev PC) squeezes the GPU; 'safe' is the user default."""
    import time as _t
    from packages.graph_scale.sense_trust_filter import (
        _isa_indegree, _reviewed_source_ids, _GENERIC_INDEGREE)

    from .device import profile
    t0 = _t.time()
    prof = profile()
    pairs, total_new, dropped = _materialize_new_edges(
        store, relation, attractor_indegree, sample_cap)

    # TRUST GATE on each candidate's object: keep only trusted types.
    try:
        indeg = _isa_indegree(store)
        reviewed_ok = bool(_reviewed_source_ids(store))
    except Exception:
        indeg = {}
        reviewed_ok = False

    def _obj_trusted(obj: str) -> bool:
        oid = store.terms.lookup(obj)
        if oid is None:
            return False
        # a modest-in-degree type is discriminative (real); a generic one is batch noise
        return int(indeg.get(oid, 0)) < _GENERIC_INDEGREE

    clean = [(a, b) for a, b in pairs if _obj_trusted(b)]
    # quality probe: clean fraction over a bounded sample (honest estimate)
    probe = pairs[:quality_probe]
    probe_clean = sum(1 for a, b in probe if _obj_trusted(b))
    clean_fraction = (probe_clean / len(probe)) if probe else 0.0

    return {
        "relation": relation, "mode": mode, "device": prof,
        "block_used": max_block_for(prof["tier"]) if mode == "max" else None,
        "total_new_provable": total_new,
        "materialized": len(pairs),
        "candidates_after_trust_gate": len(clean),
        # HONEST metric name: this is the fraction whose OBJECT is a trusted
        # (non-attractor) type — ONE dimension of cleanliness, NOT full
        # correctness. Residual base noise (a wrong stated edge inside a non-hub

        # it — which is exactly why the output is candidate-only and gated.
        "object_trusted_fraction": round(clean_fraction, 3),
        "dropped_attractors": dropped,
        "hub_subjects_excluded": True,        # polysemy hubs kept out (contamination guard)
        "seconds": round(_t.time() - t0, 2),
        "provenance_tag": f"derived:closure:{relation}",
        "written_to_production": False,       # HARD: candidate-only, operator-gated
        "honesty_note": "deductive closure is only as clean as the base graph; "
                        "these are gated candidates for evidence review, never "
                        "auto-promoted — growing numbers must not contaminate.",
        "candidates": clean[:50],             # a peek; full set is len above
    }


def closure_land(store: Any, relation: str = "is_a", *, attractor_indegree: int = 5000,
                 sample_cap: int = 5_000_000, operator_ack: bool = False,
                 dry_run: bool = True) -> dict[str, Any]:
    """LAND the deductive closure into the BASE graph AT COMPUTE SPEED — the finish of the
    learning-acceleration work. The closure computes new provable edges at ~35M/s but the old
    write path (store.add, per-triple Python loop) capped landing at ~740k/s; this keeps the
    edges in int space end-to-end and writes them with store.add_interned_batch (~35M/s, one
    numpy append per column), so writing no longer throttles learning.

    Safety is unchanged and HARD:
      * same contamination gates as closure_learn (attractor objects + polysemy hubs dropped,
        object-trust gate on each edge);
      * edges land in the BASE graph tagged `derived:closure:<relation>` — this is NOT the
        curated answer store; promotion of base→answers stays separately gated;
      * default is dry_run=True (compute + gate, write NOTHING). An actual write requires BOTH
        dry_run=False AND operator_ack=True — a real store write is operator-gated per the hard
        rule; deletion/truncation is never done here."""
    import time as _t
    from packages.graph_scale.sense_trust_filter import _isa_indegree, _GENERIC_INDEGREE
    t0 = _t.time()

    s_ids, o_ids, total_new, dropped = _materialize_new_edge_ids(
        store, relation, attractor_indegree, sample_cap)
    # INT-NATIVE trust gate on the OBJECT id (no string lookup): keep discriminative types only.
    try:
        indeg = _isa_indegree(store)
    except Exception:
        indeg = {}
    if s_ids.size and indeg:
        gen = np.array([int(indeg.get(int(b), 0)) < _GENERIC_INDEGREE for b in o_ids.tolist()],
                       dtype=bool)
        s_ids, o_ids = s_ids[gen], o_ids[gen]
    p_id = store.terms.lookup(relation)
    src = 0
    try:
        src = store.intern_source(f"derived:closure:{relation}")
    except Exception:
        pass

    written = 0
    if not dry_run and operator_ack and p_id is not None and s_ids.size:
        written = store.add_interned_batch(s_ids, int(p_id), o_ids, source=int(src), dedupe=True)
    secs = round(_t.time() - t0, 3)
    n = int(s_ids.size)
    return {
        "relation": relation,
        "total_new_provable": total_new,
        "candidates_after_gates": n,
        "dropped_attractors": dropped,
        "provenance_tag": f"derived:closure:{relation}",
        "dry_run": bool(dry_run),
        "operator_ack": bool(operator_ack),
        "written": int(written),
        "written_to_production": False,      # base graph only; answer-store promotion stays gated
        "seconds": secs,
        "land_rows_per_s": int((written or n) / secs) if secs > 0 else 0,
        "honesty_note": "provable transitive edges, contamination-gated, tagged derived; base "
                        "graph only, never auto-promoted to the answer store; a real write needs "
                        "dry_run=False AND operator_ack=True.",
    }


# ---- HYBRID CPU+GPU closure: use BOTH at once, single-node ceiling ----------
def _cpu_count_rows(A, stated_keys_sorted: np.ndarray, start: int, end: int, N: int) -> int:
    """scipy count of new provable 2-hop edges for rows [start,end) —
    VECTORIZED dedup (packed keys + searchsorted membership, no Python loop)."""
    sub = A[start:end]
    P = sub.dot(A); P.data[:] = 1
    P = P.tocoo()
    rr = P.row.astype(np.int64) + start
    cc = P.col.astype(np.int64)
    nondiag = rr != cc
    keys = (rr * N + cc)[nondiag]
    if stated_keys_sorted.size:
        pos = np.searchsorted(stated_keys_sorted, keys)
        pos = np.clip(pos, 0, stated_keys_sorted.size - 1)
        is_stated = stated_keys_sorted[pos] == keys
        return int((~is_stated).sum())
    return int(keys.size)


def _calibrate_gpu_fraction(si, oi, N, A, stated_keys, block) -> tuple[float, dict[str, Any]]:
    """Measure each device's real throughput on a small probe and return the split
    that makes them FINISH TOGETHER (neither idles). A fixed 0.5 makes the slower
    device the bottleneck — at ~1M edges the CPU is ~5x the GPU, so 0.5 leaves the
    CPU idle ~80% of the run. Balancing by measured rate is true collaboration."""
    probe = int(min(N - 1, max(64, N // 20)))
    tg = time.time()
    _gpu_rows_count(si, oi, N, 0, probe, block)
    gpu_rate = probe / max(time.time() - tg, 1e-6)
    tc = time.time()
    _cpu_count_rows(A, stated_keys, 0, probe, N)
    cpu_rate = probe / max(time.time() - tc, 1e-6)
    frac = gpu_rate / (gpu_rate + cpu_rate) if (gpu_rate + cpu_rate) > 0 else 0.5
    frac = float(min(0.95, max(0.05, frac)))
    return frac, {"gpu_rows_per_s": round(gpu_rate), "cpu_rows_per_s": round(cpu_rate),
                  "probe_rows": probe, "balanced_gpu_fraction": round(frac, 3)}


def hybrid_closure(store: Any, relation: str = "is_a", *,
                   attractor_indegree: int = 5000, gpu_fraction: float | str = 0.5,
                   exclude_hubs: bool = True) -> dict[str, Any]:
    """Run the deductive closure on CPU **and** GPU CONCURRENTLY (both release
 the GIL), each on a DISJOINT partition of the row space, then merge — the card
 and the cores work at once, never on the same rows. gpu_fraction='auto'
 calibrates the split from MEASURED device throughput so both finish together
 (no idling); a fixed float keeps the old fixed split.
 The trillion/s (' ') target is this single-node ceiling × Brain Link
 PEERS: the sharding already routes a concept's rows to one peer, so P peers
 running this hybrid aggregate ~P × (cpu+gpu) provable edges/s."""
    import threading
    import time as _t
    from scipy import sparse

    from .device import profile, safe_block

    t0 = _t.time()
    s, o = _load_relation_edges(store, relation)
    if len(s) == 0:
        return {"relation": relation, "new_edges": 0, "note": "empty"}
    obj_ids, counts = np.unique(o, return_counts=True)
    attr = set(obj_ids[counts >= attractor_indegree].tolist())
    keep = ~np.isin(o, list(attr)) if attr else np.ones(len(o), bool)
    s, o = s[keep], o[keep]
    if exclude_hubs and relation in ("is_a", "instance_of", "subclass_of"):
        subj_ids, subj_out = np.unique(s, return_counts=True)
        hubs = set(subj_ids[subj_out >= 12].tolist())
        if hubs:
            nh = ~np.isin(s, list(hubs)); s, o = s[nh], o[nh]
    nodes = np.unique(np.concatenate([s, o])); N = len(nodes)
    si = np.searchsorted(nodes, s); oi = np.searchsorted(nodes, o)
    A = sparse.csr_matrix((np.ones(len(si), np.int8), (si, oi)), shape=(N, N))
    A.data[:] = 1
    stated_keys = np.sort(si.astype(np.int64) * N + oi.astype(np.int64))

    prof = profile()
    have_gpu = prof["backend"] == "cuda"
    block = safe_block(prof["free_vram_gb"]) or 4000
    calib: dict[str, Any] = {}
    # 'auto' → use the CACHED device benchmark (measure once, reuse) for the split
    # that makes CPU+GPU finish together; fall back to a per-call probe if there is
    # no cached profile yet. A fixed float honours the caller.
    if have_gpu and gpu_fraction == "auto":
        try:
            from .device_benchmark import get_profile
            prof_dev = get_profile()
            frac = float(prof_dev.get("optimal_gpu_fraction", 0.0)) or None
            calib = {"source": "cached_benchmark", **prof_dev}
        except Exception:
            frac = None
        if not frac:
            frac, calib = _calibrate_gpu_fraction(si, oi, N, A, stated_keys, block)
        frac = float(min(0.95, max(0.05, frac)))
    else:
        frac = 0.5 if gpu_fraction == "auto" else float(gpu_fraction)
    # BALANCE the split by EDGE COUNT, not row index (edges aren't uniform per
    # row): the split point is where cumulative out-degree crosses frac,
    # so the GPU and CPU get proportional WORK, not just proportional row spans.
    if have_gpu:
        outdeg = np.bincount(si, minlength=N)
        cum = np.cumsum(outdeg)
        target = frac * cum[-1]
        split = int(np.searchsorted(cum, target)) if cum[-1] else int(N * frac)
        split = min(max(split, 1), N - 1)
    else:
        split = 0                                        # no GPU -> CPU does all rows

    results: dict[str, Any] = {}

    def _gpu_job():
        t = _t.time()
        r = _gpu_rows_count(si, oi, N, 0, split, block)
        results["gpu"] = {"new": r, "sec": round(_t.time() - t, 3), "rows": split}

    def _cpu_job():
        t = _t.time()
        r = _cpu_count_rows(A, stated_keys, split, N, N)
        results["cpu"] = {"new": r, "sec": round(_t.time() - t, 3), "rows": N - split}

    t_mm = _t.time()
    threads = []
    if have_gpu and split > 0:
        threads.append(threading.Thread(target=_gpu_job))
    threads.append(threading.Thread(target=_cpu_job))
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    mm = _t.time() - t_mm

    new_edges = results.get("gpu", {}).get("new", 0) + results.get("cpu", {}).get("new", 0)
    return {
        "relation": relation, "nodes": N, "clean_input_edges": len(s),
        "new_provable_edges": new_edges,
        "concurrent_seconds": round(mm, 3),
        "aggregate_edges_per_sec": round(new_edges / mm) if mm else 0,
        "gpu": results.get("gpu"), "cpu": results.get("cpu"),
        "split_rows": split, "gpu_fraction_used": round(frac, 3), "load_balance": calib,
        "device": prof, "used_both": bool(results.get("gpu") and results.get("cpu")),
        "trillion_path": {
            "single_node_ceiling_eps": round(new_edges / mm) if mm else 0,
            "peers_for_1e12": max(1, int(1e12 / (new_edges / mm))) if mm and new_edges else None,
            "note": "single-node CPU+GPU ceiling × Brain Link peers (concept-key "
                    "sharded, verify-by-recompute) = the honest route to 조 단위",
        },
        "total_seconds": round(_t.time() - t0, 2),
    }


def _gpu_rows_count(si, oi, N, start, end, block):
    """GPU new-edge count restricted to source rows [start,end)."""
    try:
        import torch
        from .device import is_cuda_oom
        if not torch.cuda.is_available():
            return 0
        dev = torch.device("cuda")
        idx = torch.tensor(np.vstack([si, oi]), dtype=torch.long, device=dev)
        A = torch.sparse_coo_tensor(idx, torch.ones(len(si), dtype=torch.float32, device=dev),
                                    (N, N)).coalesce()
        key1 = idx[0] * N + idx[1]
        Aidx, Aval, rows = A.indices().contiguous(), A.values().contiguous(), A.indices()[0].contiguous()

        def blk(a, b):
            m = (rows >= a) & (rows < b)
            if not bool(m.any()):
                return 0
            try:
                bi = Aidx[:, m].clone(); bi[0] -= a
                Ab = torch.sparse_coo_tensor(bi, Aval[m], (b - a, N)).coalesce()
                P = torch.sparse.mm(Ab, A).coalesce(); pi = P.indices(); r = pi[0] + a
                k2 = r * N + pi[1]
                n = int(((~torch.isin(k2, key1)) & (r != pi[1])).sum().item())
                del bi, Ab, P; torch.cuda.empty_cache()
                return n
            except RuntimeError as e:
                torch.cuda.empty_cache()
                if is_cuda_oom(e) and b - a > 1:
                    mid = (a + b) // 2
                    return blk(a, mid) + blk(mid, b)
                raise
        return sum(blk(x, min(x + block, end)) for x in range(start, end, block))
    except Exception:
        return 0


# ---- the full safe learning cycle: derive -> surgeon -> gated candidates ----
def safe_closure_learn(store: Any, relation: str = "is_a", *, mode: str = "safe",
                       attractor_indegree: int = 5000, sample_cap: int = 300000
                       ) -> dict[str, Any]:
    """The complete, contamination-safe learning cycle the owner asked for:
       derive (deductive closure) -> the SURGEON reviews every candidate in real
       time (vectorized, O(1)/edge) -> the type-disjoint ones are EXCISED ->
       what survives is a clean CANDIDATE set for the evidence gate.
    Nothing is written to production; growth cannot contaminate because the
    surgeon runs BEFORE any promotion and its incisions are audited."""
    import time as _t
    t0 = _t.time()
    pairs, total_new, dropped = _materialize_new_edges(
        store, relation, attractor_indegree, sample_cap)
    try:
        from packages.graph_scale.surgeon import precompute_families, scan_fast
        table = precompute_families(store)
        review = scan_fast(store, pairs, table)
        excised = {(i["subject"], i["object"]) for i in review["incisions"]}
        # scan_fast caps incisions at 100 for the peek; re-derive full excision set
        # by re-scanning is O(1)/edge so it's cheap — do it inline for the clean set
        clean_pairs = []
        fam_by_subj = table["fam_by_subj"]; obj_cache = table["obj_fam_cache"]
        from packages.graph_scale.surgeon import _family_of_label, _HARD_DISJOINT
        cut = 0
        for s, o in pairs:
            sid = store.terms.lookup(s)
            sf = fam_by_subj.get(sid) if sid is not None else None
            of = obj_cache.get(o) or _family_of_label(o)
            if sf and of and sf[0] != of and sf[1] >= 2 and \
                    frozenset((sf[0], of)) in _HARD_DISJOINT:
                cut += 1
                continue
            clean_pairs.append((s, o))
        surgeon_available = True
    except Exception:
        clean_pairs = pairs
        review = {"contaminated": 0, "contamination_rate": 0.0, "incisions": []}
        cut = 0
        surgeon_available = False

    return {
        "relation": relation, "mode": mode,
        "derived_provable": total_new,
        "surgeon_available": surgeon_available,
        "surgeon_excised_contaminated": cut,
        "surgeon_contamination_rate": review.get("contamination_rate", 0.0),
        "clean_candidates": len(clean_pairs),
        "dropped_attractors": dropped,
        "seconds": round(_t.time() - t0, 2),
        "provenance_tag": f"derived:closure:{relation}:surgeon-reviewed",
        "written_to_production": False,
        "pipeline": "closure(deductive) -> hub/attractor gate -> SURGEON(type-disjoint) -> gated candidates",
        "excision_sample": review.get("incisions", [])[:12],
        "candidates_sample": clean_pairs[:20],
    }


# ---- persist the surgeon-clean candidates so growth is DURABLE, not ephemeral
def persist_candidates(pairs: list[tuple[str, str]], relation: str = "is_a", *,
                       ledger_dir: str | None = None) -> dict[str, Any]:
    """Append surgeon-clean deductive candidates to a CANDIDATE LEDGER (JSONL),
    deduped, provenance-tagged. This is why the graph didn't grow: the closure
    ran but nothing was ever WRITTEN. The ledger is a candidate tier — separate
    from the base store (no single-writer risk), reversible (delete the file),
    and gated for production promotion. Returns added/skipped counts."""
    import json
    import time as _t
    from pathlib import Path

    root = Path(ledger_dir) if ledger_dir else (
        Path(__file__).resolve().parents[2] / "data" / "cloud_brain" / "derived_candidates")
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / f"{relation}_closure.jsonl"

    existing: set[tuple[str, str]] = set()
    if ledger.exists():
        with ledger.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                    existing.add((o["s"], o["o"]))
                except Exception:
                    continue
    added = 0
    ts = _t.strftime("%Y-%m-%dT%H:%M:%S")
    with ledger.open("a", encoding="utf-8") as fh:
        for s, o in pairs:
            if (s, o) in existing:
                continue
            existing.add((s, o))
            fh.write(json.dumps({"s": s, "p": relation, "o": o,
                                 "src": f"derived:closure:{relation}:surgeon-reviewed",
                                 "tier": "candidate", "at": ts}, ensure_ascii=False) + "\n")
            added += 1
    return {"ledger": str(ledger), "added": added,
            "skipped_duplicate": len(pairs) - added,
            "total_in_ledger": len(existing),
            "tier": "candidate", "written_to_production": False,
            "note": "durable clean deductive candidates; promote to production via the evidence gate"}
