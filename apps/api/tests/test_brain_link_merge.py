"""Brain Link merge wiring — the coordinator must MERGE real peer decompositions
into the persistent sharded store (the brain actually grows from peer compute).

Guards the wiring added when the merge moved from a construct-per-submit
VerifiedStore to a process-lifetime ShardedContributedStore. No live server; calls
the router's merge function directly with REAL cgsr decompositions.
"""

from __future__ import annotations

import datetime
import hashlib

import pytest

from app.routers import brain_link
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence
from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence


def _decomp_dict(text: str, i: int):
    ss = SourceSentence(
        text=text, language="en", source_id=f"bl-{i}", source_name="test",
        source_type="local_public_corpus_shard",
        source_hash=hashlib.sha256(f"{text}{i}".encode()).hexdigest()[:16],
        document_id=f"bl-{i}", title="t", url="test", license="CC BY-SA 4.0",
        usage_allowed=True,
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    decision = verify_sentence(ss, existing_dedupe_keys=set())
    if getattr(decision, "status", None) != "verified":
        return None
    dr = decompose_sentence(ss, decision, ingest_run_id="test")
    return {"concepts": dr.concepts, "relations": dr.relations,
            "case_frames": dr.case_frames, "evidence": dr.evidence}


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    # Point the singleton at a temp dir and reset it so the test never touches
    # the real contributed store.
    monkeypatch.setattr(brain_link, "_CONTRIB_STORE_ROOT_SHARDED", tmp_path / "contrib_sharded", raising=True)
    monkeypatch.setattr(brain_link, "_SHARDED_STORE", None, raising=True)
    brain_link._STORE_TOTALS["concepts_added"] = 0
    brain_link._STORE_TOTALS["relations_added"] = 0
    yield


@pytest.fixture
def decomp_dicts():
    facts = [
        "A database is an organized collection of structured information.",
        "A compiler converts source code into machine instructions.",
        "Photosynthesis converts light energy into chemical energy.",
        "A transistor amplifies or switches electronic signals.",
    ]
    out = [d for d in (_decomp_dict(t, i) for i, t in enumerate(facts)) if d is not None]
    assert out, "verification gate rejected all fixture sentences"
    return out


def test_accumulate_grows_sharded_store(isolated_store, decomp_dicts):
    added_c, added_r = brain_link._accumulate_decompositions(decomp_dicts)
    assert added_c > 0
    # the singleton was created lazily and now reports the same growth
    store = brain_link._get_sharded_store()
    assert store.status()["concepts_added_total"] == added_c
    assert store.status()["architecture"] == "persistent_hash_sharded_parallel_merge"


def test_resubmit_is_deduped(isolated_store, decomp_dicts):
    first_c, _ = brain_link._accumulate_decompositions(decomp_dicts)
    second_c, _ = brain_link._accumulate_decompositions(decomp_dicts)
    assert first_c > 0
    assert second_c == 0  # identical decompositions must not double-count


def test_empty_input_is_safe(isolated_store):
    assert brain_link._accumulate_decompositions([]) == (0, 0)


def test_pool_status_exposes_merge_engine(isolated_store, decomp_dicts):
    brain_link._accumulate_decompositions(decomp_dicts)
    status = brain_link.pool_status()
    assert status["merge_engine"] is not None
    assert status["merge_engine"]["shards"] >= 1
    assert status["store_concepts_total"] > 0
