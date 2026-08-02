# -*- coding: utf-8 -*-
"""Truth-preserving derivation accelerator — grow the graph from its own structure.

The graph already ENTAILS millions of connections it hasn't written down. is_a,
located_in and part_of are TRANSITIVE (A⊂B ∧ B⊂C ⟹ A⊂C); a few relations have
inverses. Those entailed edges are REAL new connections — logically valid given
the stated graph, never fabricated — and in a 22M-edge transitive backbone they
number in the tens of millions, latent, one hop away.

This module materializes them at store-ingest speed. It works in INTEGER space
(term ids, numpy), does ONE bounded relational join per call (a 2-hop closure
step: A→B ⋈ B→C ⟹ A→C), and is RESUMABLE via an edge cursor so a background
lane can add a steady stream every tick without ever building a full closure at
once — memory stays flat, which matters on a fragile host.

Provenance & honesty:
  * every derived edge is written with a `derived:<rel>` source tag (intern_source),
    so it is never confused with a web-verified fact;
  * the 2-hop closure is SOUND — each emitted edge follows by the relation
    algebra from two stated edges. Bad base edges (taxonomy noise) are the
    contradiction/taxonomy sweep's job, not this module's — we amplify structure,
    we do not invent it;
  * self-loops (A⊂A) and edges already stated are filtered, so the count is
    genuinely new connections, not re-writes.

This is the honest answer to "learning must keep adding connections": the web
lane adds NEW facts slowly and carefully; this lane compounds what those facts
already imply, fast.
"""
from __future__ import annotations

import time
from typing import Any

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover
    _HAVE_NP = False

# transitive relations whose 2-hop closure is sound (taxonomy / mereology / place)
TRANSITIVE = ("is_a", "subclass_of", "part_of", "located_in", "subregion_of")
# inverse pairs: a stated a—rel→b entails b—inv→a
INVERSE = {"capital": "capital_of", "capital_of": "capital",
           "author": "author_of", "author_of": "author",
           "parent_of": "child_of", "child_of": "parent_of"}

_DEFAULT_MAX_NEW = 2_000_000      # cap derived edges per call (bounds the write)
_DEFAULT_EDGE_WINDOW = 1_500_000  # cap stated edges scanned per call (bounds peak RAM)
# A real taxonomic node has 1-2 direct parents (measured on the live graph:
# is_a out-degree p50=1, p99=2). A tiny 0.45% tail has 8..1315 parents — noise
# MAGNETS where mis-parsing dumped many unrelated genera onto one node ("jigsaw
# is_a 1315 things"). Expanding a 2-hop join THROUGH such a middle explodes into
# garbage and burns the edge budget. Skip middles above this degree — a MEASURED
# discriminator (well above p99=2), not a rule table. Keeps growth clean + fast.
_DEFAULT_MAX_MIDDLE_DEGREE = 8


def _pack(a: "np.ndarray", b: "np.ndarray") -> "np.ndarray":
    """Pack two int32 id columns into one int64 key for fast set membership."""
    return (a.astype(np.int64) << 32) | (b.astype(np.int64) & 0xFFFFFFFF)


def accelerate(store: Any, *, max_new: int = _DEFAULT_MAX_NEW,
               edge_window: int = _DEFAULT_EDGE_WINDOW,
               cursor: int = 0, relations: tuple[str, ...] = TRANSITIVE,
               max_middle_degree: int = _DEFAULT_MAX_MIDDLE_DEGREE) -> dict[str, Any]:
    """Run ONE bounded derivation pass and write the new edges to the store.

    Reads a WINDOW of stated edges (bounded RAM), computes the sound 2-hop
    closure + inverse edges for that window, and appends the genuinely-new ones
    with a `derived:<rel>` source tag. Returns counts + a next-cursor to resume,
    so a background lane sweeps the whole graph across calls. Never raises into a
    loop caller: on any failure it returns an error field and adds nothing."""
    t0 = time.time()
    if not _HAVE_NP:
        return {"derived": 0, "error": "numpy_unavailable", "next_cursor": cursor}
    try:
        cols = store.open_columns()
        s = np.asarray(cols["s"]); p = np.asarray(cols["p"]); o = np.asarray(cols["o"])
        n = len(s)
        if n == 0:
            return {"derived": 0, "next_cursor": 0, "wrapped": True}
        lo = cursor % n
        hi = min(lo + edge_window, n)
        sw, pw, ow = s[lo:hi], p[lo:hi], o[lo:hi]
        terms = store.terms
        derived_pairs: list[tuple[str, np.ndarray, np.ndarray]] = []
        # transitive 2-hop closure per relation (use the FULL relation edges for
        # the join target, but only the window's sources drive the expansion — so
        # x is windowed, z ranges over all stated out-edges of x's neighbours)
        for rel in relations:
            pid = terms.lookup(rel)
            if pid is None:
                continue
            full_mask = p == pid
            if not full_mask.any():
                continue
            fa, fo = s[full_mask], o[full_mask]           # all edges of this relation
            # window's own edges of this relation drive the expansion
            wmask = pw == pid
            if not wmask.any():
                continue
            # join the window's edges (x->y) against ALL edges (y->z)
            x_new, z_new = _two_hop_join(sw[wmask], ow[wmask], fa, fo, max_new,
                                         max_middle_degree)
            if len(x_new):
                derived_pairs.append((rel, x_new, z_new))
        # inverse edges (cheap, exact): b -inv-> a for each stated a -rel-> b in window
        for rel, inv in INVERSE.items():
            pid = terms.lookup(rel)
            if pid is None:
                continue
            wmask = pw == pid
            if wmask.any():
                derived_pairs.append((inv, ow[wmask].copy(), sw[wmask].copy()))

        added = 0
        for rel, xa, za in derived_pairs:
            src_id = store.intern_source(f"derived:{rel}") if hasattr(store, "intern_source") else None
            # write via the store's add (dedups globally against stated + prior derived)
            term = terms.term
            for i in range(len(xa)):
                if store.add(term(int(xa[i])), rel, term(int(za[i])), source=src_id):
                    added += 1
                    if added >= max_new:
                        break
            if added >= max_new:
                break
        store.flush()
        dt = time.time() - t0
        return {
            "derived": added,
            "edges_scanned": int(hi - lo),
            "next_cursor": hi % n,
            "wrapped": hi >= n,
            "seconds": round(dt, 3),
            "rate_per_sec": round(added / dt) if dt > 0 else 0,
            "total": len(store),
        }
    except Exception as exc:  # pragma: no cover - never kill a loop caller
        return {"derived": 0, "error": f"{type(exc).__name__}: {exc}"[:160], "next_cursor": cursor}


def _two_hop_join(x_src: "np.ndarray", x_mid: "np.ndarray",
                  all_src: "np.ndarray", all_dst: "np.ndarray",
                  max_new: int, max_middle_degree: int = _DEFAULT_MAX_MIDDLE_DEGREE
                  ) -> tuple["np.ndarray", "np.ndarray"]:
    """(x -> mid) joined with all (mid -> z) => new (x -> z). Bounded to max_new.
    Filters self-loops, edges already stated in the full relation, and — the
    quality guard — expansion through a noise-magnet middle (out-degree above
    max_middle_degree), so the closure stays clean instead of amplifying a
    node like 'jigsaw is_a <1315 things>'."""
    if len(x_src) == 0 or len(all_src) == 0:
        return np.empty(0, np.int32), np.empty(0, np.int32)
    order = np.argsort(all_src, kind="stable")
    ss = all_src[order]; dd = all_dst[order]
    uniq, first = np.unique(ss, return_index=True)
    last = np.append(first[1:], len(ss))
    deg = last - first                                    # out-degree per uniq source
    # QUALITY GUARD (subject side): a polysemous/noise-magnet SUBJECT ('capital'
    # carrying many unrelated is_a parents) explodes into garbage regardless of
    # the middle. Drop window edges whose SUBJECT out-degree is above threshold —
    # same measured discriminator as the middle guard.
    if max_middle_degree > 0 and len(x_src):
        xp = np.searchsorted(uniq, x_src)
        xok = (xp < len(uniq)) & (uniq[np.clip(xp, 0, len(uniq) - 1)] == x_src)
        xdeg = np.where(xok, deg[np.clip(xp, 0, len(uniq) - 1)], 0)
        keep = xdeg <= max_middle_degree
        x_src, x_mid = x_src[keep], x_mid[keep]
        if len(x_src) == 0:
            return np.empty(0, np.int32), np.empty(0, np.int32)
    pos = np.searchsorted(uniq, x_mid)
    valid = (pos < len(uniq)) & (uniq[np.clip(pos, 0, len(uniq) - 1)] == x_mid)
    if not valid.any():
        return np.empty(0, np.int32), np.empty(0, np.int32)
    idx = np.nonzero(valid)[0]
    counts = (last[pos[idx]] - first[pos[idx]]).astype(np.int64)
    # QUALITY GUARD: drop expansion through noise-magnet middles (out-degree far
    # above the p99=2 of real taxonomy). Measured discriminator, not a rule table.
    if max_middle_degree > 0:
        ok = counts <= max_middle_degree
        idx, counts = idx[ok], counts[ok]
        if len(idx) == 0:
            return np.empty(0, np.int32), np.empty(0, np.int32)
    if counts.sum() > max_new:
        keep = np.cumsum(counts) <= max_new
        idx, counts = idx[keep], counts[keep]
        if counts.sum() == 0:
            idx = np.nonzero(valid)[0][:1]
            counts = np.minimum((last[pos[idx]] - first[pos[idx]]).astype(np.int64), max_new)
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, np.int32), np.empty(0, np.int32)
    x_out = np.repeat(x_src[idx], counts)
    p_start = first[pos[idx]]
    seg = np.repeat(p_start, counts) + (np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts))
    z_out = dd[seg]
    nz = x_out != z_out
    x_out, z_out = x_out[nz], z_out[nz]
    stated = _pack(all_src, all_dst); stated.sort()
    cand = _pack(x_out, z_out)
    p2 = np.searchsorted(stated, cand)
    already = (p2 < len(stated)) & (stated[np.clip(p2, 0, len(stated) - 1)] == cand)
    x_out, z_out = x_out[~already], z_out[~already]
    if len(x_out) == 0:
        return x_out, z_out
    _, ui = np.unique(_pack(x_out, z_out), return_index=True)
    return x_out[ui], z_out[ui]
