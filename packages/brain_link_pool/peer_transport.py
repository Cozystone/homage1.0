# -*- coding: utf-8 -*-
"""Peer transport client — RemoteShard makes the local router THE remote router.

Compute-offload v1 (the render model, exactly): the coordinator PARTITIONED the
tensor and SHIPPED each slice, so it retains the authoritative columns; shard
ops (degree/neighbors/closure seeds) execute on the PEER over HTTP, and
ShardRouter._verify recomputes sampled claims on the coordinator's own copy —
the requester re-renders sample frames because it holds the scene file. A peer
that lies is rejected and (peer mode) quarantined; it can never poison a
result. Storage-offload (coordinator drops its copy; verification by peer
redundancy / majority) is the later step and changes only _verify's reference,
not the routing.

RemoteShard duck-types TensorShard: same degree_of/out_neighbors surface, plus
the mirror's raw s/o columns for the verifier — so ShardRouter needs no remote
branch at all."""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from .distributed_tensor_shard import TensorShard
from .peer_shard_server import sign


class RemoteShard:
    def __init__(self, url: str, secret: str, mirror: TensorShard):
        self.url = url.rstrip("/")
        self.secret = secret
        self.shard_id = mirror.shard_id
        # authoritative verify columns (coordinator's copy of the shipped slice)
        self.s, self.p, self.o = mirror.s, mirror.p, mirror.o

    def _call(self, op: str, cid: int) -> Any:
        body = json.dumps({"op": op, "cid": int(cid)}).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json",
                     "X-Atanor-Sig": sign(self.secret, body)})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))["claim"]

    # the router calls these exactly as it calls a local TensorShard's
    def degree_of(self, concept_id: int) -> int:
        return int(self._call("degree", concept_id))

    def out_neighbors(self, concept_id: int) -> list[int]:
        return [int(x) for x in self._call("neighbors", concept_id)]

    def rows(self) -> int:
        return int(self._call("rows", -1))
