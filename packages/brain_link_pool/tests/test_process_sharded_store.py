"""ProcessShardedStore — real worker processes, real cgsr decompositions.

Verifies the Phase 2-5 contract: dedicated shard-owner processes merge in
parallel, de-dup stays EXACT across repeats (row-level concept-key routing),
and a clean shutdown leaves no orphans.
"""

from __future__ import annotations

import datetime
import hashlib

import pytest

from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence
from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence
from packages.brain_link_pool import ProcessShardedStore


def _decomp(text: str, i: int):
    ss = SourceSentence(
        text=text, language="en", source_id=f"p-{i}", source_name="test",
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


@pytest.fixture(scope="module")
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


def test_process_workers_merge_and_dedup_exactly(tmp_path, decomps):
    store = ProcessShardedStore(tmp_path / "contrib", shards=2)
    try:
        assert store.status()["workers_alive"] == 2
        first = store.accumulate(decomps)
        assert first["concepts_added"] > 0
        assert first["relations_added"] >= 0
        # EXACT global de-dup: identical rows always route to the same shard,
        # so a full replay must add nothing anywhere.
        second = store.accumulate(decomps)
        assert second["concepts_added"] == 0
        assert second["evidence_added"] == 0
        totals = store.totals()
        assert totals["concepts_added"] == first["concepts_added"]
        assert totals["batches"] == 2
        store.flush_manifests()  # must not raise; manifests written on demand
    finally:
        store.close()
    assert store.status()["workers_alive"] == 0
