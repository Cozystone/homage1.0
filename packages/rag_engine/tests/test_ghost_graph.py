from __future__ import annotations

from pathlib import Path

from knowledge_bakery import build_memory
from rag_engine.ghost_graph import PayloadVault, ghost_store_available, query_ghost_rag_context
from rag_engine.retriever import query_graphrag


def test_ghost_shell_lazy_fetch_resolves_payloads_after_hash_signal(tmp_path: Path) -> None:
    cleaned = tmp_path / "data" / "cleaned"
    ontology = tmp_path / "data" / "ontology"
    memory = tmp_path / "data" / "memory"
    cleaned.mkdir(parents=True)
    ontology.mkdir(parents=True)
    (cleaned / "ghost.md").write_text(
        "GhostTopology keeps only schematic hashes in memory. "
        "PayloadVault stores raw text on disk with SQLite WAL. "
        "Lazy Fetch emits hash signals before resolving payloads.",
        encoding="utf-8",
    )
    (ontology / "nodes.json").write_text("[]", encoding="utf-8")
    (ontology / "edges.json").write_text("[]", encoding="utf-8")

    build_memory(str(cleaned), str(ontology), str(memory))

    assert ghost_store_available(str(memory))
    ghost = query_ghost_rag_context("How does Lazy Fetch use PayloadVault?", str(memory))
    assert ghost["system_state"] == "GHOST SHELL ACTIVE"
    assert ghost["active_hashes"]
    assert ghost["payload_docs"]
    assert ghost["fetch_logs"][0].startswith("[FETCH] Emitting signal for")
    assert ghost["fetch_logs"][1] == "[FETCH] Payloads resolved. Synthesizing response."

    resolved = PayloadVault(str(memory)).resolve_payloads(ghost["active_hashes"], limit=22)
    assert resolved
    assert all("raw_text" in item for item in resolved)

    rag = query_graphrag("How does Lazy Fetch use PayloadVault?", memory_dir=str(memory))
    assert rag["ghost_shell"]["system_state"] == "GHOST SHELL ACTIVE"
    assert rag["fetch_sequence"][0].startswith("[FETCH] Emitting signal for")
    assert rag["retrieval_trace"]["active_hashes"]
