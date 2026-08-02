# -*- coding: utf-8 -*-
"""Turbo bulk ingest — the Gemini spec's PRINCIPLES, measured against OUR profile.

WHAT THE SPEC GOT RIGHT (adopted):
  * batch-buffer-then-binary-flush (we already do columnar int32 appends)
  * post-hoc async audit instead of per-row gating FOR THE CURATED LANE
  * fixed-width binary rows (ours: 12B/triple int32 SPO + 4B source)

WHAT THE SPEC GOT WRONG FOR US (rejected, honestly):
  * "disk I/O and locks are the bottleneck" — measured, they are NOT: the
    584k/s ceiling is per-triple Python interpreter overhead (3 dict interns,
    a set probe, 4 list appends PER TRIPLE). mmap/lock-free buys nothing here.
  * GPU tensor parsing at 50-100M nodes/s — conflates memcpy with
    understanding; our extraction cost IS the quality gates (anchor/judge/
    consensus), which stay. Curated dumps arrive pre-parsed anyway.
  * integrity bypass as a general mode — the exact learning-noise disaster we
    already paid to fix. Turbo is CURATED-LANE ONLY (Wikidata/ConceptNet class
    sources, verified upstream); the web-learning lane keeps every gate.

THE ACTUAL ACCELERANT (this module): vectorize the interpreter away.
  * np.unique over the batch's flat string column -> C-speed dedup of terms;
    the Python intern loop runs over UNIQUE terms only (curated dumps reuse
    predicates/objects heavily, so uniques ≪ 3n)
  * ids = uniq_ids[inverse]  (one vectorized gather)
  * in-batch exact row dedup via void-view np.unique (12-byte rows)
  * single binary append per column per batch
Cross-RUN dedup moves to the ASYNC AUDIT SWEEP (audit_sweep below) — the
spec's requirement 1, realized as a stable-order global np.unique rewrite.
"""
from __future__ import annotations

import time
from typing import Any, Iterable

import numpy as np


def turbo_ingest(store: Any, triples: Iterable[tuple[str, str, str]],
                 source: int | None = None) -> dict[str, Any]:
    """Vectorized bulk append for CURATED sources. Exact de-dup within the
    batch; cross-run de-dup is the audit sweep's job (turbo rows are marked in
    meta as audit-pending). Returns measured counts + rate."""
    # This module writes the column files directly for throughput, so it must
    # cross the same substrate guard as TripleStore.add()/flush() *before*
    # materialising input or taking an empty-input fast path.  Otherwise a
    # canonical shipped store can be damaged before _write_meta() eventually
    # notices that it is read-only.
    store._require_writable("turbo ingest")
    rows = triples if isinstance(triples, list) else list(triples)
    n = len(rows)
    if n == 0:
        return {"ingested": 0, "rate_per_sec": 0.0}
    t0 = time.time()
    store.flush()  # settle any buffered rows first (single writer discipline)

    # 1) term interning at C++ speed: pyarrow dictionary_encode is a HASH

    #    obtained as a wheel, no toolchain, no custom native code to maintain.
    #    Fallback: np.unique (sort-based, ~parity with the classic path).
    terms = store.terms
    intern = terms.intern
    try:
        import pyarrow as pa

        flat = pa.concat_arrays([
            pa.array([r[0] for r in rows], type=pa.string()),
            pa.array([r[1] for r in rows], type=pa.string()),
            pa.array([r[2] for r in rows], type=pa.string()),
        ])
        enc = flat.dictionary_encode()
        uniq = enc.dictionary.to_pylist()      # unique terms only
        inverse = enc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    except Exception:
        flat_np = np.empty(3 * n, dtype=object)
        for k, (s, p, o) in enumerate(rows):
            flat_np[k] = s
            flat_np[n + k] = p
            flat_np[2 * n + k] = o
        uniq_arr, inverse = np.unique(flat_np.astype("U"), return_inverse=True)
        uniq = [str(t) for t in uniq_arr]
    uniq_ids = np.empty(len(uniq), dtype=np.int32)
    for i, t in enumerate(uniq):
        uniq_ids[i] = intern(t)
    ids = uniq_ids[inverse]
    s_col, p_col, o_col = ids[:n], ids[n:2 * n], ids[2 * n:]

    # 2) exact in-batch row de-dup: 12-byte void view -> np.unique, first-kept
    packed = np.empty((n, 3), dtype=np.int32)
    packed[:, 0], packed[:, 1], packed[:, 2] = s_col, p_col, o_col
    void = np.ascontiguousarray(packed).view(
        np.dtype((np.void, packed.dtype.itemsize * 3))).ravel()
    _, first_idx = np.unique(void, return_index=True)
    first_idx.sort()  # stable original order
    kept = packed[first_idx]
    m = len(kept)

    # 3) single binary append per column (+ aligned source ids)
    store.terms.flush()
    for j, name in enumerate(("s", "p", "o")):
        with (store.root / f"{name}.col").open("ab") as fh:
            fh.write(np.ascontiguousarray(kept[:, j]).tobytes())
    src = np.full(m, int(source or 0), dtype=np.int32)
    store._ensure_src_backfilled(store.root / "src.col",
                                 store._count + m, store._count) \
        if hasattr(store, "_ensure_src_backfilled") else None
    with (store.root / "src.col").open("ab") as fh:
        fh.write(src.tobytes())

    store._count += m
    store._write_meta({"turbo_audit_pending": True,
                       "turbo_last_batch": m})
    dt = time.time() - t0
    return {"ingested": m, "in_batch_deduped": n - m,
            "unique_terms": int(len(uniq)),
            "seconds": round(dt, 4),
            "rate_per_sec": round(m / dt) if dt > 0 else 0}


def turbo_ingest_tsv(store: Any, tsv_path: str, source: int | None = None,
                     block_size: int = 64 << 20) -> dict[str, Any]:
    """The REAL fast lane: file -> store with Python objects never materializing.
    Curated dumps are files anyway (Wikidata/ConceptNet TSV), so parsing,
    dictionary-hashing and column building all stay inside Arrow's C++ kernels;
    Python only walks the UNIQUE terms to keep the TermDict authoritative.
    Cross-run de-dup remains the audit sweep's job (turbo contract)."""
    # Guard before importing Arrow or opening the caller-selected input.  A
    # read-only shipped store must reject the operation without side effects
    # even when the TSV is empty, missing, or malformed.
    store._require_writable("turbo TSV ingest")
    import pyarrow as pa
    from pyarrow import csv as pacsv

    t0 = time.time()
    store.flush()
    table = pacsv.read_csv(
        tsv_path,
        parse_options=pacsv.ParseOptions(delimiter="\t"),
        read_options=pacsv.ReadOptions(
            column_names=["s", "p", "o"], block_size=block_size),
    )
    n = table.num_rows
    if n == 0:
        return {"ingested": 0, "rate_per_sec": 0.0}
    flat = pa.concat_arrays([
        table.column("s").combine_chunks().cast(pa.string()),
        table.column("p").combine_chunks().cast(pa.string()),
        table.column("o").combine_chunks().cast(pa.string()),
    ])
    enc = flat.dictionary_encode()
    uniq = enc.dictionary.to_pylist()
    inverse = enc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    intern = store.terms.intern
    uniq_ids = np.empty(len(uniq), dtype=np.int32)
    for i, t in enumerate(uniq):
        uniq_ids[i] = intern(t if t is not None else "")
    ids = uniq_ids[inverse]

    packed = np.empty((n, 3), dtype=np.int32)
    packed[:, 0], packed[:, 1], packed[:, 2] = ids[:n], ids[n:2 * n], ids[2 * n:]
    void = np.ascontiguousarray(packed).view(
        np.dtype((np.void, packed.dtype.itemsize * 3))).ravel()
    _, first_idx = np.unique(void, return_index=True)
    first_idx.sort()
    kept = packed[first_idx]
    m = len(kept)

    store.terms.flush()
    for j, name in enumerate(("s", "p", "o")):
        with (store.root / f"{name}.col").open("ab") as fh:
            fh.write(np.ascontiguousarray(kept[:, j]).tobytes())
    with (store.root / "src.col").open("ab") as fh:
        fh.write(np.full(m, int(source or 0), dtype=np.int32).tobytes())
    store._count += m
    store._write_meta({"turbo_audit_pending": True, "turbo_last_batch": m})
    dt = time.time() - t0
    return {"ingested": m, "rows_read": n, "in_batch_deduped": n - m,
            "unique_terms": len(uniq), "seconds": round(dt, 4),
            "rows_per_sec": round(n / dt) if dt > 0 else 0}


def audit_sweep(store: Any) -> dict[str, Any]:
    """The async ' ' pass (spec requirement 1, our safety frame):
 a stable-order global exact de-dup rewrite of the columns. Turbo batches
 skip the incremental seen-set; THIS restores global exactness afterwards,
 off the hot path. Provenance rows stay aligned."""
    # audit_sweep rewrites every column with numpy.tofile(), bypassing the
    # ordinary TripleStore mutation methods.  Deny canonical shipped stores
    # before any scan or rewrite.
    store._require_writable("turbo audit sweep")
    t0 = time.time()
    store.flush()
    cols = {}
    for name in ("s", "p", "o", "src"):
        path = store.root / f"{name}.col"
        if not path.exists():
            return {"swept": 0, "removed": 0}
        cols[name] = np.fromfile(str(path), dtype=np.int32)
    n = len(cols["s"])
    if len(cols["src"]) < n:  # legacy tier: pad source column
        cols["src"] = np.concatenate(
            [cols["src"], np.zeros(n - len(cols["src"]), dtype=np.int32)])
    packed = np.empty((n, 3), dtype=np.int32)
    packed[:, 0], packed[:, 1], packed[:, 2] = cols["s"][:n], cols["p"][:n], cols["o"][:n]
    void = np.ascontiguousarray(packed).view(
        np.dtype((np.void, packed.dtype.itemsize * 3))).ravel()
    _, first_idx = np.unique(void, return_index=True)
    first_idx.sort()
    removed = n - len(first_idx)
    if removed:
        for j, name in enumerate(("s", "p", "o")):
            np.ascontiguousarray(packed[first_idx, j]).tofile(
                str(store.root / f"{name}.col"))
        np.ascontiguousarray(cols["src"][first_idx]).tofile(
            str(store.root / "src.col"))
        store._count = len(first_idx)
    store._write_meta({"turbo_audit_pending": False,
                       "last_audit_removed": int(removed),
                       "last_audit_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"swept": n, "removed": int(removed),
            "seconds": round(time.time() - t0, 4)}
