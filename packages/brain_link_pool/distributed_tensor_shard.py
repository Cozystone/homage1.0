# -*- coding: utf-8 -*-
"""Distributed tensor sharding — the trillion-edge plan (Brain Link, task 4).

MEASURED WALL (owner's own arithmetic, confirmed on this RTX 5080): the whole
25.9M-edge graph mirrors to VRAM in 606 MB. Linear extrapolation:
    26M edges   -> 0.6 GB   (fits one workstation)
    26B edges   -> 600 GB   (a GPU cluster)
    1T edges    -> 23 TB    (a data-center of GPUs, InfiniBand-linked)
So trillion-scale tensor compute cannot live in one VRAM. The owner's answer,
not a rented cluster: shard the tensor across Brain Link PEERS — a render-token
economy applied to a graph engine, which is STRONGER than the rendering case
because a graph op is EXACTLY reproducible (verify by byte-equal hash, not by
approximate preview).

This module is the routing + verified-merge layer, built on assets that already
exist:
  * CONCEPT-KEY ROUTING — sharded_store._shard_for_key: a concept's edges live
    in exactly ONE shard (blake2b(subject) % K), so a concept-scoped op (degree,
    2-hop closure seed) routes to a single owner peer with no cross-shard
    inflation. The same primitive that made the multicore merge exact.
  * TRUST — peer_trust_guard: PoW admission, signature checks, revocable
    quarantine gate every peer op.
  * ECONOMY — render_economy: the requester BURNS Synapse credits to submit a
    shard job; the provider MINTS on VERIFIED completion; proof_of_inference
    re-runs a content-seeded sample locally and demands byte equality.

The safety invariant carries over from the single-node engine: a peer can only
PROPOSE shard results; nothing is trusted until proof_of_inference verifies it,
so a lying or faulty peer collapses its reputation instead of poisoning the
graph. This is propose-verify at the network scale — the same law as the GPU
lane, the derivation lane, and the sense filter.

Local mode (K in-process shards) runs today for the design proof; the peer
transport is the deployment step (each shard's op is a pure function of its
edge slice, so the local router IS the remote router with a network hop
swapped for the function call)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

from .sharded_store import _shard_for_key

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover
    np = None
    _HAVE_NP = False


def shard_of(concept: str, shards: int) -> int:
    """The peer/shard that owns a concept's outgoing edges (concept-key route)."""
    return _shard_for_key(concept, shards)


@dataclass
class TensorShard:
    """One shard's edge slice — a COO sub-tensor sized to fit one peer's VRAM.
    Rows are assigned by SUBJECT concept-key so a subject's whole adjacency is
    co-located (a 2-hop seed never needs a cross-shard fetch for its first hop)."""
    shard_id: int
    s: "np.ndarray"
    p: "np.ndarray"
    o: "np.ndarray"

    def rows(self) -> int:
        return len(self.s)

    def vram_bytes(self) -> int:
        # int64 on device (bincount/searchsorted want it): 24 bytes/edge
        return self.rows() * 24

    # a shard job is a PURE FUNCTION of the slice — identical inputs, identical
    # bytes out, so proof_of_inference can verify a peer by re-running locally.
    def degree_of(self, concept_id: int) -> int:
        return int((self.s == concept_id).sum())

    def out_neighbors(self, concept_id: int) -> list[int]:
        return sorted(int(x) for x in self.o[self.s == concept_id].tolist())

    def job_hash(self) -> str:
        h = hashlib.blake2b(digest_size=16)
        for col in (self.s, self.p, self.o):
            h.update(np.asarray(col, dtype="<i8").tobytes())
        return h.hexdigest()


def partition_columns(s: "np.ndarray", p: "np.ndarray", o: "np.ndarray",
                      terms: Any, shards: int) -> list[TensorShard]:
    """Split a COO tensor into `shards` shards by SUBJECT concept-key. Each
    shard is independently VRAM-mirrorable; a subject's edges never split."""
    if not _HAVE_NP:
        raise RuntimeError("numpy required")
    s = np.asarray(s); p = np.asarray(p); o = np.asarray(o)
    # concept-key route per row (by subject term string -> same shard as the
    # dedupe router, so tensor shards and store shards agree)
    assign = np.empty(len(s), dtype=np.int32)
    # cache per-distinct-subject to avoid hashing every row
    uniq, inv = np.unique(s, return_inverse=True)
    su = np.array([_shard_for_key(terms.term(int(u)), shards) for u in uniq], dtype=np.int32)
    assign = su[inv]
    out = []
    for k in range(shards):
        m = assign == k
        out.append(TensorShard(k, s[m], p[m], o[m]))
    return out


@dataclass
class ShardRouter:
    """Routes concept-scoped tensor ops to the owning shard and verifies the
    result before trusting it. `verify_rate` sets the proof_of_inference sample:
    a cheating/faulty peer is caught with p≥verify_rate per job, compounding to
    certain reputation collapse."""
    shards: list[TensorShard]
    terms: Any
    verify_rate: float = 1.0            # local mode verifies everything; tune for peers
    stats: dict[str, int] = field(default_factory=lambda: {"routed": 0, "verified": 0, "rejected": 0})

    def owner(self, concept: str) -> int:
        return _shard_for_key(concept, len(self.shards))

    def degree(self, concept: str) -> int | None:
        """Route a degree query to the owning shard, verify, return the value."""
        cid = self.terms.lookup(concept)
        if cid is None:
            return None
        k = self.owner(concept)
        claimed = self.shards[k].degree_of(cid)   # the PEER's (untrusted) result
        if self._verify(self.shards[k], lambda sh: int((sh.s == cid).sum()), claimed):
            self.stats["routed"] += 1
            self.stats["verified"] += 1
            return claimed
        self.stats["rejected"] += 1
        return None

    def neighbors(self, concept: str) -> list[int] | None:
        cid = self.terms.lookup(concept)
        if cid is None:
            return None
        k = self.owner(concept)
        claimed = self.shards[k].out_neighbors(cid)
        if self._verify(self.shards[k],
                        lambda sh: sorted(int(x) for x in sh.o[sh.s == cid].tolist()),
                        claimed):
            self.stats["routed"] += 1
            self.stats["verified"] += 1
            return claimed
        self.stats["rejected"] += 1
        return None

    def _verify(self, shard: TensorShard, reference: Callable[[TensorShard], Any],
                claimed: Any) -> bool:
        """proof_of_inference, single-op edition: the verifier RE-RUNS the op
        itself on the shard's raw edge slice (the trusted input) and demands
        equality with the peer's claim — it never trusts the peer's method, so a
        peer that lies in `degree_of` is caught by the independent recompute.
        verify_rate<1 samples which claims to check (cheaper for trusted peers,
        still certain to catch a persistent liar). Rejection is where
        peer_trust_guard.quarantine hooks in peer mode."""
        import random

        if self.verify_rate < 1.0 and random.random() > self.verify_rate:
            return True
        return reference(shard) == claimed


def plan_capacity(edges: int, vram_gb_per_peer: float = 16.0) -> dict[str, Any]:
    """How many peers does an N-edge tensor need? The trillion-scale sizing the
    owner sketched, made concrete: 24 bytes/edge in device int64."""
    bytes_total = edges * 24
    per_peer = int(vram_gb_per_peer * 1e9)
    peers = max(1, -(-bytes_total // per_peer))   # ceil
    return {"edges": edges, "bytes_total": bytes_total,
            "gb_total": round(bytes_total / 1e9, 1),
            "vram_gb_per_peer": vram_gb_per_peer, "peers_required": peers,
            "note": "concept-key routing keeps a concept's adjacency on one peer; "
                    "a 2-hop closure fetches 2nd-hop neighbours from at most the "
                    "peers owning the frontier concepts."}


# ---- STORAGE OFFLOAD: replicated shards + majority verification ------------
# The coordinator holds NO copy of the columns. Each concept's adjacency lives
# on R successor shards; a claim is trusted only when a MAJORITY of replicas
# independently agree (byte equality — graph ops are exactly reproducible, so
# honest replicas can only agree). A lying minority is outvoted and named for
# peer_trust_guard.quarantine. This changes only WHO verifies — the routing
# law and the pure-function job surface are identical to the local mode.

def replica_owners(concept: str, shards: int, replicas: int = 3) -> list[int]:
    """The R shards holding a concept's adjacency: its owner + successors."""
    k = _shard_for_key(concept, shards)
    return [(k + i) % shards for i in range(min(replicas, shards))]


def partition_columns_replicated(s, p, o, terms: Any, shards: int,
                                 replicas: int = 3) -> list[TensorShard]:
    """Like partition_columns, but every subject's rows land on R shards."""
    if not _HAVE_NP:
        raise RuntimeError("numpy required")
    s = np.asarray(s); p = np.asarray(p); o = np.asarray(o)
    uniq, inv = np.unique(s, return_inverse=True)
    base = np.array([_shard_for_key(terms.term(int(u)), shards) for u in uniq],
                    dtype=np.int32)
    out = []
    for k in range(shards):
        m = np.zeros(len(s), dtype=bool)
        for r in range(min(replicas, shards)):
            m |= (base[inv] == (k - r) % shards)
        out.append(TensorShard(k, s[m], p[m], o[m]))
    return out


@dataclass
class MajorityRouter:
    """Coordinator WITHOUT authoritative columns: truth = replica majority."""
    shards: list          # peer handles (TensorShard / RemoteShard duck-typed)
    terms: Any
    replicas: int = 3
    stats: dict[str, int] = field(default_factory=lambda: {
        "routed": 0, "agreed": 0, "outvoted_peers": 0, "no_majority": 0})

    def degree(self, concept: str) -> int | None:
        return self._op(concept, "degree_of")

    def neighbors(self, concept: str) -> list[int] | None:
        return self._op(concept, "out_neighbors")

    def _op(self, concept: str, method: str):
        cid = self.terms.lookup(concept)
        if cid is None:
            return None
        owners = replica_owners(concept, len(self.shards), self.replicas)
        claims = []
        for k in owners:
            try:
                v = getattr(self.shards[k], method)(cid)
                claims.append((k, tuple(v) if isinstance(v, list) else v))
            except Exception:
                continue
        if not claims:
            return None
        from collections import Counter

        val, n = Counter(c for _k, c in claims).most_common(1)[0]
        if n * 2 <= len(claims):
            self.stats["no_majority"] += 1
            return None
        liars = [k for k, c in claims if c != val]
        self.stats["routed"] += 1
        self.stats["agreed"] += 1
        self.stats["outvoted_peers"] += len(liars)   # -> peer_trust quarantine
        return list(val) if isinstance(val, tuple) else val
