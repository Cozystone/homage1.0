from __future__ import annotations

from pathlib import Path

import pytest

from packages.graph_scale import graph_paths


def test_shipped_reader_and_each_legacy_producer_are_disjoint() -> None:
    shipped = graph_paths.SHIPPED_GRAPH_ROOT.resolve()
    fragments = {
        graph_paths.ABSTAIN_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.BULK_INGEST_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.SENSORY_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.VISUAL_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.WEB_KNOWLEDGE_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.STRUCTURED_PROFILE_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.RELATION_MINER_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.KNOWLEDGE_HARVEST_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.KAIKKI_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.URIMALSEM_PROPOSAL_FRAGMENT_ROOT.resolve(),
        graph_paths.WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT.resolve(),
    }

    assert len(fragments) == 11
    assert shipped not in fragments
    assert all(
        graph_paths.GRAPH_MUTATION_SPOOL_ROOT.resolve() in path.parents
        for path in fragments
    )
    assert all(shipped not in path.parents for path in fragments)


@pytest.mark.parametrize(
    "producer_id",
    ["", "../escape", "UPPER", "white space", "a" * 65],
)
def test_legacy_proposal_root_rejects_unsafe_ids(producer_id: str) -> None:
    with pytest.raises(ValueError):
        graph_paths.legacy_proposal_fragment_root(producer_id)


def test_graph_path_contract_contains_no_symlink_indirection() -> None:
    for path in (
        graph_paths.SHIPPED_GRAPH_ROOT,
        graph_paths.GRAPH_MUTATION_SPOOL_ROOT,
    ):
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            if current.exists():
                assert not current.is_symlink()


def test_mutation_batch_root_is_unique_and_confined(tmp_path: Path) -> None:
    batches = tmp_path / "batches"
    batch_id = "gmb_" + "a" * 32

    computed = graph_paths.mutation_batch_root(
        batch_id,
        batches_root=batches,
    )
    assert computed == batches.resolve() / batch_id
    assert not computed.exists()

    created = graph_paths.create_mutation_batch_root(
        batch_id,
        batches_root=batches,
    )
    marker = created / "preserve.txt"
    marker.write_text("partial bytes stay visible", encoding="utf-8")
    with pytest.raises(FileExistsError):
        graph_paths.create_mutation_batch_root(
            batch_id,
            batches_root=batches,
        )
    assert marker.read_text(encoding="utf-8") == "partial bytes stay visible"


@pytest.mark.parametrize(
    "batch_id",
    [
        "",
        "../gmb_" + "a" * 32,
        "gmb_" + "A" * 32,
        "gmb_" + "a" * 31,
        "gmb_" + "a" * 33,
        "other_" + "a" * 32,
        "gmb_" + "a" * 16 + "/" + "b" * 16,
    ],
)
def test_mutation_batch_root_rejects_unsafe_ids(
    tmp_path: Path,
    batch_id: str,
) -> None:
    with pytest.raises(ValueError):
        graph_paths.mutation_batch_root(
            batch_id,
            batches_root=tmp_path / "batches",
        )


def test_mutation_batches_root_cannot_alias_shipped_graph() -> None:
    with pytest.raises(ValueError):
        graph_paths.mutation_batch_root(
            "gmb_" + "b" * 32,
            batches_root=graph_paths.SHIPPED_GRAPH_ROOT,
        )


def test_graph_path_identity_is_normalized() -> None:
    assert graph_paths.same_graph_path(
        graph_paths.SHIPPED_GRAPH_ROOT / ".." / "kg_triples",
        graph_paths.SHIPPED_GRAPH_ROOT,
    )
    assert graph_paths.is_shipped_graph_root(
        graph_paths.SHIPPED_GRAPH_ROOT
    )
    assert not graph_paths.is_shipped_graph_root(
        graph_paths.GRAPH_MUTATION_SPOOL_ROOT
    )


def test_core_reader_and_write_guard_share_canonical_root() -> None:
    from packages.graph_scale import answer_bridge, triple_store

    assert graph_paths.same_graph_path(
        answer_bridge._ROOT,
        graph_paths.SHIPPED_GRAPH_ROOT,
    )
    assert graph_paths.same_graph_path(
        triple_store._CANONICAL_SHIPPED_ROOT,
        graph_paths.SHIPPED_GRAPH_ROOT,
    )
