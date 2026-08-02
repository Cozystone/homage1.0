# -*- coding: utf-8 -*-
"""Answers precomputed at build time, so a question costs a hash and a binary search.

    from packages.atanor_index.property_table import PropertyTable
    t = PropertyTable("data/atanor_index/property_table")
    t.lookup("trowel", "used_for")            # -> [("digging", "wikipedia"), ("spreading", ...)]
    t.lookup_many(entities, relations)        # vectorized; this is the one that goes fast

WHY THIS IS NOT A FASTER SEARCH ENGINE. It is a different data structure, chosen because ATANOR's
queries are not a person's queries. A person types ambiguous language and needs ranking, so a search
engine must tokenize, score thousands of postings and sort -- the local BM25 index does exactly that and
answers in 20-800 ms. ATANOR never types anything ambiguous: by the time it asks, the shape parser has
already produced (entity, relation). That is not a search, it is a KEY LOOKUP, and a key lookup that
still runs BM25 is paying for a ranking nobody reads.

A human search engine CANNOT do this, and the reason is worth being precise about: it does not know the
shape of the question in advance, so it cannot precompute the answer. ATANOR does know -- the relations
are a small closed set the shape parser recognises -- so the extraction that used to run per query runs
ONCE over the whole corpus at build time and the result is stored as a table.

    per query, before   tokenize -> hash -> searchsorted -> score N postings -> sort -> regex the text
    per query, after    hash the (entity, relation) -> searchsorted -> slice

WHAT IT COSTS, stated up front. The relation set is frozen into the build: adding capable_of after the
fact means rebuilding, and a build is minutes. Precomputation also means the table can only answer what
the extractor could see, so its recall is the extractor's recall and no better -- this makes retrieval
free, it does not make extraction smarter.

The corpus id per value is kept because the consensus gate counts DISTINCT SOURCES, so a lookup has to
say not just what was found but where. Same rule, same floor, just no longer paid for at query time.

On-disk layout, all memmap so open() costs no RAM:
    keys.npy         uint64[K]   sorted blake2b of "entity\\x00relation"
    val_offsets.npy  int64[K+1]  slice bounds into the value arrays
    val_obj.npy      int32[V]    object string id
    val_corpus.npy   uint8[V]    which corpus asserted it
    obj_offsets.npy  int64[O+1]  byte bounds into the blob
    obj_blob.bin                 utf-8 object strings, interned once
    meta.json        {corpora, relations, n_keys, n_values, built_at}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np


def key64(entity: str, relation: str) -> int:
    """Stable 64-bit key. Same hashing idiom as disk_index, so one collision story covers both."""
    h = hashlib.blake2b(f"{entity.strip().lower()}\x00{relation.strip().lower()}".encode("utf-8"),
                        digest_size=8)
    return int.from_bytes(h.digest(), "big", signed=False)


def key64_many(entities: Iterable[str], relations: Iterable[str]) -> np.ndarray:
    return np.fromiter((key64(e, r) for e, r in zip(entities, relations)),
                       dtype=np.uint64, count=-1)


class PropertyTableBuilder:
    """Accumulate (entity, relation, object, corpus) then write the memmap table.

    Deduplicated on (key, object, corpus): the same corpus asserting a thing twice is one sighting, and
    counting it twice would let a single source reach a two-source floor on its own."""

    def __init__(self) -> None:
        self._rows: dict[int, set[tuple[str, int]]] = {}
        self.corpora: list[str] = []

    def corpus_id(self, name: str) -> int:
        if name not in self.corpora:
            self.corpora.append(name)
        return self.corpora.index(name)

    def add(self, entity: str, relation: str, obj: str, corpus: str) -> None:
        e, o = entity.strip().lower(), obj.strip().lower()
        if not e or not o:
            return
        self._rows.setdefault(key64(e, relation), set()).add((o, self.corpus_id(corpus)))

    def __len__(self) -> int:
        return len(self._rows)

    def write(self, out_dir: str | Path, relations: list[str]) -> dict:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        keys = np.array(sorted(self._rows), dtype=np.uint64)
        strings: dict[str, int] = {}
        blob = bytearray()
        obj_off = [0]

        def intern(s: str) -> int:
            if s not in strings:
                strings[s] = len(obj_off) - 1
                blob.extend(s.encode("utf-8"))
                obj_off.append(len(blob))
            return strings[s]

        val_obj: list[int] = []
        val_corp: list[int] = []
        val_off = [0]
        for k in keys:
            for o, c in sorted(self._rows[int(k)]):
                val_obj.append(intern(o))
                val_corp.append(c)
            val_off.append(len(val_obj))

        np.save(out / "keys.npy", keys)
        np.save(out / "val_offsets.npy", np.array(val_off, dtype=np.int64))
        np.save(out / "val_obj.npy", np.array(val_obj, dtype=np.int32))
        np.save(out / "val_corpus.npy", np.array(val_corp, dtype=np.uint8))
        np.save(out / "obj_offsets.npy", np.array(obj_off, dtype=np.int64))
        (out / "obj_blob.bin").write_bytes(bytes(blob))
        meta = {"n_keys": int(len(keys)), "n_values": int(len(val_obj)),
                "n_objects": int(len(strings)), "corpora": self.corpora,
                "relations": relations}
        (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta


class PropertyTable:
    """Read-only lookup. Every array is memmapped, so opening costs no RAM regardless of table size."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.meta = json.loads((self.root / "meta.json").read_text(encoding="utf-8"))
        self.corpora: list[str] = list(self.meta.get("corpora") or [])
        self._keys = np.load(self.root / "keys.npy", mmap_mode="r")
        self._voff = np.load(self.root / "val_offsets.npy", mmap_mode="r")
        self._vobj = np.load(self.root / "val_obj.npy", mmap_mode="r")
        self._vcor = np.load(self.root / "val_corpus.npy", mmap_mode="r")
        self._ooff = np.load(self.root / "obj_offsets.npy", mmap_mode="r")
        self._blob = np.memmap(self.root / "obj_blob.bin", dtype=np.uint8, mode="r")

    def __len__(self) -> int:
        return int(len(self._keys))

    def _obj(self, oid: int) -> str:
        a, b = int(self._ooff[oid]), int(self._ooff[oid + 1])
        return bytes(self._blob[a:b]).decode("utf-8", "ignore")

    def _rows_at(self, pos: int) -> list[tuple[str, str]]:
        a, b = int(self._voff[pos]), int(self._voff[pos + 1])
        return [(self._obj(int(self._vobj[i])), self.corpora[int(self._vcor[i])])
                for i in range(a, b)]

    def lookup(self, entity: str, relation: str) -> list[tuple[str, str]]:
        """(object, corpus) pairs, or empty. One hash and one binary search — no text is touched."""
        k = np.uint64(key64(entity, relation))
        pos = int(np.searchsorted(self._keys, k))
        if pos >= len(self._keys) or np.uint64(self._keys[pos]) != k:
            return []
        return self._rows_at(pos)

    def lookup_many(self, entities, relations) -> list[list[tuple[str, str]]]:
        """The batch path, and the one that reaches the throughput the table exists for.

        searchsorted is vectorized, so N queries cost ONE numpy call over the whole key array rather
        than N python-level searches. Building the string results is the remaining per-hit cost, which
        is why `count_many` exists for callers that only need whether consensus is reachable."""
        ks = key64_many(entities, relations)
        pos = np.searchsorted(self._keys, ks)
        pos_c = np.clip(pos, 0, len(self._keys) - 1)
        hit = np.asarray(self._keys)[pos_c] == ks
        return [self._rows_at(int(p)) if h else [] for p, h in zip(pos_c, hit)]

    def count_many(self, entities, relations) -> np.ndarray:
        """Distinct-corpus count per query, with no strings built at all. This is what the consensus
        floor actually needs, and it stays inside numpy end to end."""
        ks = key64_many(entities, relations)
        pos = np.clip(np.searchsorted(self._keys, ks), 0, len(self._keys) - 1)
        hit = np.asarray(self._keys)[pos] == ks
        out = np.zeros(len(ks), dtype=np.int32)
        voff = np.asarray(self._voff)
        vcor = np.asarray(self._vcor)
        for i in np.flatnonzero(hit):
            a, b = int(voff[pos[i]]), int(voff[pos[i] + 1])
            out[i] = len(np.unique(vcor[a:b]))
        return out
