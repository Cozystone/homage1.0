"""Disk-backed BM25 inverted index — the ATANOR Index V0 core ( §1 Ring 1 ).

openbook.ContentIndex holds every posting in RAM; that caps it at ~10^5 passages. The full EN-wiki
lead corpus is 7.0M passages, so V0 promotes the index to disk ( §2 " - ").

Design (int-columnar, matching world_pack's memmap philosophy so open() costs ~0 RAM):
 * Terms are keyed by a STABLE 64-bit blake2b hash — no per-query term→id dict to hold in RAM.
 Collision odds for ~5M terms at 64 bits ≈ 7e-7 (negligible; a collision only pollutes one
 posting list with a few extra docs, ranked out by BM25). Query = hash + np.searchsorted.
 * Build uses SPIMI external merge: stream docs, buffer (term_hash, doc_id, tf) postings, flush
 sorted runs when the RAM budget trips, then k-way merge runs by term_hash. RAM stays bounded
 by the run budget, not the corpus — 7M docs index on a laptop.

On-disk layout (all under out_dir/):
 term_hashes.npy uint64[T] sorted unique term hashes
 post_offsets.npy int64[T+1] cumulative offsets into postings/postings_tf
 postings.npy int32[P] doc_ids, grouped by term, sorted within group
 postings_tf.npy uint8[P] term freq in that doc (capped 255)
 doc_offsets.npy int64[D] byte offset of each doc line in the source .tsv
 doc_len.npy int32[D] token count per doc (BM25 length norm)
 meta.json {n_docs, n_terms, n_postings, avgdl, source_tsv, built_at, hub_cut}
No LLM anywhere — pure corpus statistics.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import time
from pathlib import Path

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
# Compact English function-word stop set — dropped from postings (can't discriminate, bloat the index).
_STOP = frozenset((
    "the a an and or but of to in on at for with by from as is are was were be been being this that "
    "these those it its it's he she they them his her their our your my we you i not no than then so "
    "such into over under out up down off about above below between within without also more most "
    "some any all each both few many other another which who whom whose what when where why how there "
    "here can could may might must shall should will would do does did done has have had having".split()
))
_TF_CAP = 255
_BM25_K1, _BM25_B = 1.5, 0.75


def _hash64(term: str) -> int:
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest(), "big")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) >= 2 and t not in _STOP]


# ----------------------------------------------------------------------------- build
def build_index(source_tsv: str | Path, out_dir: str | Path, *,
                ram_postings: int = 12_000_000, n_bucket_bits: int = 6,
                progress_every: int = 500_000) -> dict:
    """Build a disk-backed BM25 index from a title\\ttext .tsv. Returns the meta dict.
    ram_postings caps the in-RAM posting buffer before a bucket flush (12M ≈ ~200MB across buffers).
    n_bucket_bits sets 2^bits hash buckets; peak merge RAM ≈ total_postings/2^bits (6→/64)."""
    source_tsv = Path(source_tsv)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    buckets_dir = out_dir / "_buckets"
    buckets_dir.mkdir(exist_ok=True)
    t0 = time.time()


    # Postings are partitioned into 2^n_bucket_bits buckets by the TOP bits of the term hash. Two
    # consequences: (a) every posting of a given term lands in ONE bucket, so grouping is complete
    # per bucket; (b) bucket index ascends with hash, so processing buckets 0..B-1 yields globally
    # sorted term_hashes (→ query stays an O(log T) searchsorted). Peak RAM = one bucket ≈ total/B,

    n_buckets = 1 << n_bucket_bits
    shift = 64 - n_bucket_bits
    buf_h: list[list[int]] = [[] for _ in range(n_buckets)]
    buf_d: list[list[int]] = [[] for _ in range(n_buckets)]
    buf_t: list[list[int]] = [[] for _ in range(n_buckets)]
    buffered = 0

    def flush_buckets() -> None:
        nonlocal buffered
        for b in range(n_buckets):
            if not buf_h[b]:
                continue
            with open(buckets_dir / f"{b:03d}.h", "ab") as fh:
                fh.write(np.asarray(buf_h[b], dtype=np.uint64).tobytes())
            with open(buckets_dir / f"{b:03d}.d", "ab") as fd:
                fd.write(np.asarray(buf_d[b], dtype=np.int32).tobytes())
            with open(buckets_dir / f"{b:03d}.t", "ab") as ft:
                ft.write(np.asarray(buf_t[b], dtype=np.uint8).tobytes())
            buf_h[b].clear(); buf_d[b].clear(); buf_t[b].clear()
        buffered = 0

    doc_offsets: list[int] = []
    doc_len: list[int] = []
    with open(source_tsv, "rb") as f:
        doc_id = 0
        offset = 0
        for raw in f:
            doc_offsets.append(offset)
            offset += len(raw)
            title, _, text = raw.decode("utf-8", "replace").partition("\t")
            toks = tokenize(title + " " + text)
            doc_len.append(len(toks))
            tf_local: dict[str, int] = {}
            for tok in toks:
                tf_local[tok] = tf_local.get(tok, 0) + 1        # tf per unique term in this doc
            for tok, c in tf_local.items():
                h = _hash64(tok)
                b = h >> shift
                buf_h[b].append(h); buf_d[b].append(doc_id); buf_t[b].append(min(c, _TF_CAP))
                buffered += 1
            doc_id += 1
            if buffered >= ram_postings:
                flush_buckets()
            if progress_every and doc_id % progress_every == 0:
                print(f"  [build] {doc_id:,} docs, {time.time()-t0:.0f}s", flush=True)
    flush_buckets()

    n_docs = len(doc_offsets)
    np.save(out_dir / "doc_offsets.npy", np.asarray(doc_offsets, dtype=np.int64))
    dl = np.asarray(doc_len, dtype=np.int32)
    np.save(out_dir / "doc_len.npy", dl)
    avgdl = float(dl.mean()) if n_docs else 0.0
    del doc_offsets, doc_len, dl

    # ---- bucket-wise merge: each bucket sorts+groups in RAM; postings streamed to a memmap ----
    total_post = sum((buckets_dir / f"{b:03d}.d").stat().st_size // 4
                     for b in range(n_buckets) if (buckets_dir / f"{b:03d}.d").exists())
    post_docs = np.lib.format.open_memmap(out_dir / "postings.npy", mode="w+",
                                          dtype=np.int32, shape=(total_post,))
    post_tfs = np.lib.format.open_memmap(out_dir / "postings_tf.npy", mode="w+",
                                         dtype=np.uint8, shape=(total_post,))
    term_hashes_list: list[np.ndarray] = []
    post_off_list: list[np.ndarray] = []
    written = 0
    for b in range(n_buckets):
        hp = buckets_dir / f"{b:03d}.h"
        if not hp.exists():
            continue
        h = np.fromfile(hp, dtype=np.uint64)
        d = np.fromfile(buckets_dir / f"{b:03d}.d", dtype=np.int32)
        t = np.fromfile(buckets_dir / f"{b:03d}.t", dtype=np.uint8)
        order = np.lexsort((d, h))            # by term_hash, then doc_id
        h = h[order]; d = d[order]; t = t[order]
        m = len(h)
        post_docs[written:written + m] = d
        post_tfs[written:written + m] = t
        uniq, starts = np.unique(h, return_index=True)   # sorted within bucket → globally sorted
        term_hashes_list.append(uniq.astype(np.uint64))
        post_off_list.append((starts + written).astype(np.int64))
        written += m
        for suf in ("h", "d", "t"):
            (buckets_dir / f"{b:03d}.{suf}").unlink(missing_ok=True)
    post_docs.flush(); post_tfs.flush()
    del post_docs, post_tfs

    if term_hashes_list:
        term_hashes_arr = np.concatenate(term_hashes_list)
        post_off = np.append(np.concatenate(post_off_list), total_post).astype(np.int64)
    else:
        term_hashes_arr = np.zeros(0, np.uint64)
        post_off = np.zeros(1, np.int64)
    np.save(out_dir / "term_hashes.npy", term_hashes_arr)
    np.save(out_dir / "post_offsets.npy", post_off)

    try:
        buckets_dir.rmdir()
    except OSError:
        pass

    meta = {
        "n_docs": n_docs, "n_terms": int(len(term_hashes_arr)), "n_postings": total_post,
        "avgdl": avgdl, "source_tsv": str(source_tsv.resolve()),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "build_seconds": round(time.time() - t0, 1),
        "hub_cut_frac": 0.02, "n_bucket_bits": n_bucket_bits,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  [build] DONE {n_docs:,} docs · {len(term_hashes_arr):,} terms · {total_post:,} postings · "
          f"{meta['build_seconds']}s", flush=True)
    return meta


# ----------------------------------------------------------------------------- query
class DiskIndex:
    """Read-only BM25 query over a built index. open() only memmaps arrays → ~0 RAM regardless of size."""

    def __init__(self, index_dir: str | Path):
        self.dir = Path(index_dir)
        self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        self.term_hashes = np.load(self.dir / "term_hashes.npy", mmap_mode="r")
        self.post_offsets = np.load(self.dir / "post_offsets.npy", mmap_mode="r")
        self.postings = np.load(self.dir / "postings.npy", mmap_mode="r")
        self.postings_tf = np.load(self.dir / "postings_tf.npy", mmap_mode="r")
        self.doc_offsets = np.load(self.dir / "doc_offsets.npy", mmap_mode="r")
        self.doc_len = np.load(self.dir / "doc_len.npy", mmap_mode="r")
        self.n_docs = int(self.meta["n_docs"])
        self.avgdl = float(self.meta["avgdl"]) or 1.0
        self.hub_cut = max(50, int(self.meta.get("hub_cut_frac", 0.02) * self.n_docs))
        self._src = open(self.meta["source_tsv"], "rb")

    def _term_slice(self, term: str):
        h = np.uint64(_hash64(term))
        i = int(np.searchsorted(self.term_hashes, h))
        if i >= len(self.term_hashes) or int(self.term_hashes[i]) != int(h):
            return None
        return int(self.post_offsets[i]), int(self.post_offsets[i + 1])

    def _fetch(self, doc_id: int) -> tuple[str, str]:
        self._src.seek(int(self.doc_offsets[doc_id]))
        line = self._src.readline().decode("utf-8", "replace")
        title, _, text = line.partition("\t")
        return title.strip(), text.rstrip("\n")

    def search_topk(self, query: str, k: int = 5, *, min_score: float = 0.0) -> list[dict]:
        """Return up to k docs scored by BM25 (Okapi, k1=1.5 b=0.75) + a title-match boost.
        The boost is the field-weighting real search engines use: a doc whose TITLE carries the query
        terms is the on-topic article, so it should beat docs that merely mention them in the body
        (measured: "chemical formula of water" → 'Water', not 'Oleum'). Empty list if nothing matches."""
        toks = set(tokenize(query))
        if not toks:
            return []
        scores: dict[int, float] = {}
        for tok in toks:
            sl = self._term_slice(tok)
            if sl is None:
                continue
            lo, hi = sl
            df = hi - lo
            if df == 0 or df > self.hub_cut:          # skip hub tokens (present in >2% of docs)
                continue
            idf = math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))
            docs = np.asarray(self.postings[lo:hi])
            tfs = np.asarray(self.postings_tf[lo:hi]).astype(np.float32)
            dl = np.asarray(self.doc_len[docs]).astype(np.float32)
            denom = tfs + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / self.avgdl)
            contrib = idf * (tfs * (_BM25_K1 + 1.0)) / np.maximum(denom, 1e-6)
            for did, sc in zip(docs.tolist(), contrib.tolist()):
                scores[did] = scores.get(did, 0.0) + sc
        if not scores:
            return []
        # Rerank a wider BM25 shortlist by (BM25 × title-canonicality); only the shortlist fetches.
        # Canonicality = how fully the QUERY explains the TITLE = |q∩title| / |title|. A title with
        # extra words the query never mentioned is a derivative/disambiguation page, not the canonical
        # article: "Speed of light" (2/2=1.0) must beat "Variable speed of light" (2/3) and "Hamlet"
        # (1/1) must beat "Hamlet (Liszt)" (1/2). Measured on the 7M corpus — plain per-term boost
        # over-selected short stub pages; dividing by title length is what demotes them.
        # Generous shortlist floor: the canonical long article ranks LOW in raw BM25 (length norm
        # penalty) and would fall outside a tight top-k, so it would never get the subset boost.
        # Title fetches are cheap (~a few dozen disk seeks), so rerank a wide net.
        shortlist = heapq.nlargest(max(k * 4, 40), scores.items(), key=lambda kv: kv[1])
        raw_q = set(_TOKEN.findall(query.lower()))
        maxb = max((sc for _, sc in shortlist), default=1.0) or 1.0
        out = []
        for did, sc in shortlist:
            title, text = self._fetch(did)
            ttoks = set(tokenize(title))
            # Title canonicality is an ADDITIVE bonus (× shortlist max BM25), not multiplicative:
            # short disambiguation stubs have runaway BM25 (length norm), so a multiplicative boost
            # loses the arms race. An exact title (⊆ query, 0 extra RAW words like you/and/the) is
            # THE article and must dominate; a padded/derivative title gets a smaller, decaying bonus.
            if ttoks and ttoks <= toks:
                extra_raw = len(set(_TOKEN.findall(title.lower())) - raw_q)
                canon = 2.0 if extra_raw == 0 else 1.0 / (1.0 + extra_raw)
            else:
                canon = 0.4 * (len(toks & ttoks) / len(ttoks)) if ttoks else 0.0
            final = float(sc) + canon * maxb
            out.append({"title": title, "text": text, "doc_id": did,
                        "score": round(final, 3), "bm25": round(float(sc), 3)})
        out.sort(key=lambda r: -r["score"])
        return [r for r in out[:k] if r["score"] >= min_score]

    def close(self) -> None:
        try:
            self._src.close()
        except Exception:
            pass
