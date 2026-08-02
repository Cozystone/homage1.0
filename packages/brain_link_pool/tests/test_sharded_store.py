"""ShardedContributedStore correctness — real cgsr decompositions, no mocks."""

from __future__ import annotations

import datetime
import hashlib

import pytest

from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence
from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence
from packages.brain_link_pool import ShardedContributedStore


def _decomp(text: str, i: int):
    ss = SourceSentence(
        text=text, language="en", source_id=f"t-{i}", source_name="test",
        source_type="local_public_corpus_shard",
        source_hash=hashlib.sha256(f"{text}{i}".encode()).hexdigest()[:16],
        document_id=f"d-{i}", title="t", url="test", license="CC BY-SA 4.0",
        usage_allowed=True,
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    decision = verify_sentence(ss, existing_dedupe_keys=set())
    if getattr(decision, "status", None) != "verified":
        return None
    return decompose_sentence(ss, decision, ingest_run_id="test")


@pytest.fixture
def decomps():
    facts = [
        "A database is an organized collection of structured information.",
        "A compiler converts source code into machine instructions.",
        "A neuron transmits electrical signals across synapses.",
        "Photosynthesis converts light energy into chemical energy.",
        "An enzyme accelerates a chemical reaction in the body.",
        "A transistor amplifies or switches electronic signals.",
    ]
    out = [d for d in (_decomp(t, i) for i, t in enumerate(facts)) if d is not None]
    assert out, "verification gate rejected all fact sentences — fixture is broken"
    return out


def test_accumulate_adds_concepts(tmp_path, decomps):
    store = ShardedContributedStore(tmp_path / "contrib", shards=4)
    res = store.accumulate(decomps)
    assert res["concepts_added"] > 0
    assert store.totals()["concepts_added"] == res["concepts_added"]
    assert store.totals()["batches"] == 1


def test_replay_is_deduped_within_shards(tmp_path, decomps):
    store = ShardedContributedStore(tmp_path / "contrib", shards=4)
    first = store.accumulate(decomps)
    second = store.accumulate(decomps)  # identical replay -> same source_hash -> same shard
    assert first["concepts_added"] > 0
    # Re-submitting the exact same decompositions must not re-add them.
    assert second["concepts_added"] == 0
    assert second["concepts_deduped"] >= 0


def test_dedup_is_exact_regardless_of_shard_count(tmp_path, decomps):
    """The whole point of row-level (concept-key) routing: the SAME data merged
    into 1 shard vs 8 shards must add the SAME number of concepts — no per-shard
    duplication. (The old decomposition-by-source routing inflated 8 shards ~8x.)"""
    one = ShardedContributedStore(tmp_path / "one", shards=1).accumulate(decomps)
    eight = ShardedContributedStore(tmp_path / "eight", shards=8).accumulate(decomps)
    assert one["concepts_added"] > 0
    assert eight["concepts_added"] == one["concepts_added"]
    assert eight["relations_added"] == one["relations_added"]


def test_routing_is_deterministic_and_bounded(tmp_path, decomps):
    from packages.brain_link_pool.sharded_store import _shard_for_key

    for k in (1, 4, 8):
        keys = ["alpha", "beta", "gamma", ""]
        for key in keys:
            s = _shard_for_key(key, k)
            assert s == _shard_for_key(key, k)  # deterministic
            assert 0 <= s < k


def test_shard_count_one_still_works(tmp_path, decomps):
    store = ShardedContributedStore(tmp_path / "contrib", shards=1)
    res = store.accumulate(decomps)
    assert res["concepts_added"] > 0


def test_status_shape(tmp_path, decomps):
    store = ShardedContributedStore(tmp_path / "contrib", shards=2)
    store.accumulate(decomps)
    st = store.status()
    assert st["architecture"] == "persistent_hash_sharded_parallel_merge"
    assert st["shards"] == 2
    assert st["concepts_added_total"] >= 0
    assert "deduped" in st
