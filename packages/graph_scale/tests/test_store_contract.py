"""Store contracts: producers stage; readers use signed shipped generations."""

from __future__ import annotations

from pathlib import Path


def test_graph_producers_never_default_to_the_shipped_read_store():
    """Default writers are isolated fragments, not canonical mutation aliases."""
    import scripts.bulk_ingest_kg as ingest
    from packages.knowledge_harvest import ingest as harvest_ingest
    from packages.graph_scale import abstain_feeder, answer_bridge
    from packages.graph_scale.graph_paths import (
        GRAPH_MUTATION_SPOOL_ROOT,
        SHIPPED_GRAPH_ROOT,
    )

    shipped = Path(answer_bridge._ROOT).resolve()
    bulk_stage = Path(ingest.DEFAULT_ROOT).resolve()
    abstain_stage = Path(
        abstain_feeder.PROPOSAL_FRAGMENT_ROOT
    ).resolve()
    harvest_stage = Path(harvest_ingest.DEFAULT_ROOT).resolve()

    assert shipped == SHIPPED_GRAPH_ROOT.resolve()
    assert bulk_stage != shipped
    assert abstain_stage != shipped
    assert harvest_stage != shipped
    assert bulk_stage != abstain_stage
    assert GRAPH_MUTATION_SPOOL_ROOT.resolve() in bulk_stage.parents
    assert GRAPH_MUTATION_SPOOL_ROOT.resolve() in abstain_stage.parents
    assert GRAPH_MUTATION_SPOOL_ROOT.resolve() in harvest_stage.parents


def test_legacy_apply_clis_are_confined_to_distinct_proposal_fragments():
    from packages.graph_scale import graph_paths
    import scripts.ingest_kaikki as kaikki
    import scripts.urimalsaem_drain as urimalsaem
    import scripts.wikidata_term_resolver as wikidata_terms

    roots = {
        Path(kaikki.KAIKKI_PROPOSAL_FRAGMENT_ROOT).resolve(),
        Path(urimalsaem.URIMALSEM_PROPOSAL_FRAGMENT_ROOT).resolve(),
        Path(
            wikidata_terms.WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT
        ).resolve(),
    }
    assert len(roots) == 3
    assert graph_paths.SHIPPED_GRAPH_ROOT.resolve() not in roots
    assert all(
        graph_paths.GRAPH_MUTATION_SPOOL_ROOT.resolve() in root.parents
        for root in roots
    )


def test_abstain_queue_single_path():
    """The recorder and staged-fragment consumer share one pending queue."""
    from packages.graph_scale import abstain_queue

    assert abstain_queue.QUEUE_PATH.name == "abstain_queue.jsonl"
    assert "graph_scale" in str(abstain_queue.QUEUE_PATH)


def test_pack_promoter_writes_what_loader_reads():
    """Graph-pack promotion and the live pack loader share the sealed path."""
    from packages.base_brain.models import PACK_PATH as writer_path
    from packages.base_brain.pack_loader import PACK_PATH as reader_path

    assert Path(writer_path).resolve() == Path(reader_path).resolve()
