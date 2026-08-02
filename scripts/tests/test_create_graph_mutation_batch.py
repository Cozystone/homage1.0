"""The proposal compiler binds immutable batches to the exact live base."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import create_graph_mutation_batch as compiler
import landing_chain_lib as landing
from packages.graph_scale.mutation_batch import (
    MutationStage,
    validate_mutation_batch,
)
from packages.graph_scale.triple_store import TripleStore


def _store(root: Path) -> None:
    store = TripleStore(root)
    store.add("france", "capital", "lyon")
    store.flush()
    if hasattr(store.terms, "close"):
        store.terms.close()


def _proposal(path: Path, base_digest: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": compiler.PROPOSAL_SCHEMA,
                "producer_id": "compiler_test",
                "producer_run_id": "run-001",
                "expected_base_digest_sha256": base_digest,
                "additions": [
                    {
                        "subject": "france",
                        "predicate": "capital",
                        "object": "paris",
                        "provenance": "curated:test",
                        "source_refs": ["urn:test:paris"],
                    }
                ],
                "retractions": [
                    {
                        "subject": "france",
                        "predicate": "capital",
                        "object": "lyon",
                        "reason": "corrected by reviewed source",
                        "evidence_refs": ["urn:test:correction"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_compile_proposal_reaches_proposed_without_mutating_live(
    tmp_path: Path,
) -> None:
    live = tmp_path / "kg_triples"
    batches = tmp_path / "batches"
    proposal = tmp_path / "proposal.json"
    _store(live)
    before = landing._tree_sha256(live)
    _proposal(proposal, before)

    result = compiler.compile_proposal(
        proposal,
        shipped_root=live,
        batches_root=batches,
    )

    assert landing._tree_sha256(live) == before
    assert result["production_store_mutated"] is False
    validation = validate_mutation_batch(result["batch_root"])
    assert validation.ok is True
    assert validation.latest_stage is MutationStage.PROPOSED


def test_compile_proposal_rejects_stale_base_without_creating_batch(
    tmp_path: Path,
) -> None:
    live = tmp_path / "kg_triples"
    batches = tmp_path / "batches"
    proposal = tmp_path / "proposal.json"
    _store(live)
    _proposal(proposal, "0" * 64)
    before = landing._tree_sha256(live)

    with pytest.raises(ValueError, match="base digest"):
        compiler.compile_proposal(
            proposal,
            shipped_root=live,
            batches_root=batches,
        )

    assert landing._tree_sha256(live) == before
    assert not batches.exists()


def test_compile_proposal_rejects_extra_or_duplicate_json_fields(
    tmp_path: Path,
) -> None:
    live = tmp_path / "kg_triples"
    _store(live)
    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        '{"schema_version":"x","schema_version":"x"}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="strict JSON"):
        compiler.compile_proposal(
            proposal,
            shipped_root=live,
            batches_root=tmp_path / "batches",
        )
