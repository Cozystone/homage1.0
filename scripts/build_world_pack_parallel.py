# -*- coding: utf-8 -*-
"""Full Wikidata dump → world pack — PARALLEL-PARSE variant (uses all cores).

Same schema + same extraction as build_world_pack.py (byte-identical triples on the same input),
but the CPU-bound JSON parse + extract runs across a worker Pool instead of one core.

Why: the serial build measured ~2,600 entities/s at ~36% of a 32-core box — indexed_bzip2 can
decompress ~26k lines/s but the single-threaded `json.loads`+extract throttled the pipeline. Here
the main process only reads (decompression stays parallel in the C++ lib), fans batches of raw
lines out to `--workers` parse processes, and is the SINGLE writer of the store (same contract as
serial). Correctness is preserved by reusing the EXACT extract logic below.

  python scripts/build_world_pack_parallel.py --limit 200000 --workers 24   # benchmark a slice
  python scripts/build_world_pack_parallel.py --workers 28                   # full build
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

try:
    import orjson as _fastjson
    _loads = _fastjson.loads
except ImportError:                                    # pragma: no cover
    _loads = json.loads

REPO = Path(__file__).resolve().parents[1]

# ── EXACT copy of the serial extractor's constants (correctness contract) ─────────────────────
_SKIP_P31 = {"Q13442814", "Q7318358", "Q591041", "Q871232"}
_RELS = {
    "P31": "is_a", "P279": "subclass_of", "P36": "capital", "P17": "country",
    "P1082": "population", "P2046": "area", "P571": "inception", "P50": "author",
    "P61": "discovered_by", "P170": "creator", "P19": "born_in", "P569": "birth_date",
    "P106": "occupation", "P361": "part_of", "P527": "has_part", "P828": "caused_by",
}


def _first_claim_ids(claims: dict, pid: str, k: int = 2) -> list[str]:
    out = []
    for c in (claims.get(pid) or [])[:k]:
        try:
            v = c["mainsnak"]["datavalue"]["value"]
            if isinstance(v, dict) and "id" in v:
                out.append(str(v["id"]))
            elif isinstance(v, dict) and "amount" in v:
                out.append(str(v["amount"]).lstrip("+"))
            elif isinstance(v, dict) and "time" in v:
                out.append(str(v["time"])[1:11])
        except Exception:
            continue
    return out


def _prescreen_skip(line: bytes) -> bool:
    """Cheap byte test — True ⇒ skip without parsing (same rule as serial)."""
    return (b'"ko"' not in line and b'"en"' not in line) or \
           (b"Q13442814" in line and b'"ko"' not in line)


def _extract(line: bytes) -> tuple[list[tuple[str, str, str]], bool, bool]:
    """Return (triples, kept, skipped_article) for ONE raw line — identical to the serial loop."""
    if line.endswith(b","):
        line = line[:-1]
    try:
        e = _loads(line)
    except Exception:
        return [], False, False
    if e.get("type") != "item":
        return [], False, False
    claims = e.get("claims") or {}
    p31 = set(_first_claim_ids(claims, "P31", 3))
    if p31 & _SKIP_P31:
        return [], False, True
    labels = e.get("labels") or {}
    lab_ko = (labels.get("ko") or {}).get("value")
    lab_en = (labels.get("en") or {}).get("value")
    label = lab_ko or lab_en
    if not label:
        return [], False, False
    out: list[tuple[str, str, str]] = []
    qid = str(e.get("id") or "")
    descs = e.get("descriptions") or {}
    d_ko = (descs.get("ko") or {}).get("value")
    d_en = (descs.get("en") or {}).get("value")
    if d_ko:
        out.append((label, "defined_as", d_ko))
    if d_en:
        out.append((label, "defined_as", d_en))
    if lab_ko and lab_en and lab_ko != lab_en:
        out.append((lab_ko, "alias", lab_en))
    for al in ((e.get("aliases") or {}).get("ko") or [])[:4]:
        v = al.get("value")
        if v and v != label:
            out.append((label, "alias", v))
    if qid:
        out.append((qid, "qlabel", label))
    for pid, pred in _RELS.items():
        for tgt in _first_claim_ids(claims, pid):
            out.append((label, pred, tgt))
    return out, True, False


def _parse_batch(batch: list[bytes]) -> tuple[list[tuple[str, str, str]], int, int, int]:
    """Worker: prescreen + extract a batch. Returns (triples, kept, skipped_article, parsed)."""
    triples: list[tuple[str, str, str]] = []
    kept = skipped = parsed = 0
    for line in batch:
        if _prescreen_skip(line):
            continue
        parsed += 1
        ts, k, sk = _extract(line)
        if k:
            kept += 1
            triples.extend(ts)
        elif sk:
            skipped += 1
    return triples, kept, skipped, parsed


def _line_batches(raw, limit: int | None, batch_size: int, batch_bytes: int = 2_000_000):
    """Yield lists of raw (stripped) lines, bounded by COUNT and by BYTES.

    The byte bound is the crash fix (2026-07-15 postmortem): wikidata entities run 5-50KB, so
    2,000-line batches reached ~100MB; with dozens in flight the pool's task pipe exhausted
    kernel resources (WinError 1450) on a 31GB box. ≤2MB batches keep total in-flight pickle
    volume to tens of MB regardless of entity size."""
    batch: list[bytes] = []
    bbytes = 0
    seen = 0
    for line in raw:
        if limit and seen >= limit:
            break
        seen += 1
        line = line.strip()
        if len(line) < 10:
            continue
        batch.append(line)
        bbytes += len(line)
        if len(batch) >= batch_size or bbytes >= batch_bytes:
            yield batch, seen
            batch = []
            bbytes = 0
    if batch:
        yield batch, seen


def build(limit: int | None = None, workers: int = 0, batch_size: int = 1000) -> dict:
    import multiprocessing as mp

    dump = Path(os.environ.get("WORLD_PACK_DUMP", "C:/0.ASKIM ALL-VIN/wikidata/latest-all.json.bz2"))
    dst = REPO / "data" / "graph_scale" / os.environ.get("WORLD_PACK_OUT", "world_pack_parallel")
    journal = REPO / "data" / "graph_scale" / "world_pack_build.jsonl"
    if not dump.exists():
        print("dump not found:", dump)
        return {}
    sys.path.insert(0, str(REPO))
    from packages.graph_scale.triple_store import TripleStore

    dst.mkdir(parents=True, exist_ok=True)
    st = TripleStore(dst, dict_backend="sharded", write_src=False)
    # postmortem defaults (31GB box): the single-writer main is the throughput ceiling (~2.2x
    # serial), so 10 workers deliver nearly the same speed as 28 at a third of the memory.
    workers = workers or 10

    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=8)   # 8 decomp threads outrun the pipeline
        backend = f"indexed_bzip2(8)+pool({workers})"
    except Exception:
        import bz2
        raw = bz2.BZ2File(str(dump), "rb")
        backend = f"bz2(serial)+pool({workers})"

    def _free_ram_gb() -> float:
        """System free physical memory, GB (ctypes — no dependency)."""
        try:
            import ctypes
            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS(); ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return ms.ullAvailPhys / 1e9
        except Exception:
            return 99.0                                   # non-Windows / failure → guard disabled

    t0 = time.time()
    seen = kept = skipped_article = triples = parsed = 0
    pool = mp.Pool(processes=workers)
    from collections import deque

    pending: deque = deque()
    max_inflight = workers * 2   # ≤ workers*2 batches × ≤2MB ≈ tens of MB in pipes, hard-bounded

    def _consume(res) -> None:
        nonlocal kept, skipped_article, triples, parsed
        tr, k, sk, pa = res.get()
        kept += k
        skipped_article += sk
        parsed += pa
        for s, p, o in tr:
            st.add(s, p, o)
        triples += len(tr)
        if kept // 100_000 > (kept - k) // 100_000:            # crossed a 100k-kept milestone
            st.flush()
            dt = time.time() - t0
            row = {"at": time.strftime("%H:%M:%S"), "seen_parsed": parsed, "kept": kept,
                   "skipped_articles": skipped_article, "triples": triples,
                   "rate_parsed_s": round(parsed / max(1e-9, dt), 1), "backend": backend}
            print(json.dumps(row), flush=True)
            journal.parent.mkdir(parents=True, exist_ok=True)
            with journal.open("a", encoding="utf-8") as jf:
                jf.write(json.dumps(row) + "\n")

    try:
        n_batches = 0
        for batch, _s in _line_batches(raw, limit, batch_size):
            pending.append(pool.apply_async(_parse_batch, (batch,)))
            batch = None                                        # drop main's reference immediately
            n_batches += 1
            if len(pending) >= max_inflight:                    # bound memory: drain oldest
                _consume(pending.popleft())
            if n_batches % 500 == 0 and _free_ram_gb() < 3.0:   # pressure guard: drain fully,
                while pending:                                  # never race the OS to a 1450
                    _consume(pending.popleft())
        while pending:                                          # drain the tail
            _consume(pending.popleft())
    finally:
        pool.close()
        pool.join()
        try:
            raw.close()
        except Exception:
            pass
        st.flush()

    dt = time.time() - t0
    disk = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file()) / 1e9
    rep = {"parsed": parsed, "kept": kept, "skipped_articles": skipped_article,
           "triples": triples, "elapsed_s": round(dt, 1),
           "rate_parsed_s": round(parsed / max(1e-9, dt), 1),
           "disk_gb": round(disk, 2), "workers": workers, "backend": backend}
    print("\nDONE", json.dumps(rep))
    return rep


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    lim = None
    wk = 0
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            lim = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        elif a.startswith("--workers"):
            wk = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    raise SystemExit(0 if build(lim, wk) else 1)
