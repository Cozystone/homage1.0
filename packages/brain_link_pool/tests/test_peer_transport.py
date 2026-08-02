# -*- coding: utf-8 -*-
"""The transport layer proves the design's one-liner: the local router IS the
remote router. Real TCP round-trips (ThreadingHTTPServer on localhost), signed
requests, and a lying peer caught by the coordinator's independent recompute."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from packages.brain_link_pool.distributed_tensor_shard import ShardRouter, TensorShard
from packages.brain_link_pool.peer_shard_server import ShardHandler
from packages.brain_link_pool.peer_transport import RemoteShard
from packages.brain_link_pool.sharded_store import _shard_for_key

SECRET = "test-pool"


class _Terms:
    def __init__(self, names):
        self._t = {n: i for i, n in enumerate(names)}

    def lookup(self, t):
        return self._t.get(t)


def _slice(shard_id, s, o):
    s = np.asarray(s)
    return TensorShard(shard_id, s, np.zeros(len(s), dtype=np.int64), np.asarray(o))


def _serve(shard: TensorShard, port: int, lie=False):
    handler = type("H", (ShardHandler,), {
        "slice_data": {"s": shard.s, "o": shard.o, "shard_id": shard.shard_id},
        "secret": SECRET, "lie": lie})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture()
def peers():
    servers = []
    yield servers
    for s in servers:
        s.shutdown()


def test_remote_router_equals_local(peers):
    names = [f"c{i}" for i in range(20)]
    terms = _Terms(names)
    s = np.array([7] * 5 + [3] * 3)
    o = np.arange(8) + 100
    slices = []
    for k in range(2):
        rows = [i for i in range(8) if _shard_for_key(names[s[i]], 2) == k]
        slices.append(_slice(k, s[rows], o[rows]))
    local = ShardRouter(shards=slices, terms=terms)
    peers.append(_serve(slices[0], 18871))
    peers.append(_serve(slices[1], 18872))
    remote_shards = [RemoteShard(f"http://127.0.0.1:{18871 + k}", SECRET, slices[k])
                     for k in range(2)]
    remote = ShardRouter(shards=remote_shards, terms=terms)
    for c in ("c7", "c3"):
        assert remote.degree(c) == local.degree(c)
        assert remote.neighbors(c) == local.neighbors(c)
    assert remote.stats["rejected"] == 0
    assert remote.stats["verified"] >= 4


def test_unsigned_request_refused(peers):
    peers.append(_serve(_slice(0, np.array([1, 1]), np.array([2, 3])), 18873))
    body = json.dumps({"op": "degree", "cid": 1}).encode()
    req = urllib.request.Request("http://127.0.0.1:18873", data=body,
                                 headers={"X-Atanor-Sig": "forged"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 403


def test_lying_peer_rejected_by_recompute(peers):
    names = ["a", "b"]
    terms = _Terms(names)
    sl = _slice(0, np.array([0, 0, 1]), np.array([5, 6, 7]))
    peers.append(_serve(sl, 18874, lie=True))     # inflates degree claims
    remote = ShardRouter(
        shards=[RemoteShard("http://127.0.0.1:18874", SECRET, sl)], terms=terms)
    victim = "a" if _shard_for_key("a", 1) == 0 else "b"
    assert remote.degree(victim) is None          # claim != coordinator recompute
    assert remote.stats["rejected"] == 1
