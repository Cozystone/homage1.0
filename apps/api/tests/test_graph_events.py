from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.ingestion_stream import CleanedDirectoryWatcher, GraphEventHub, format_sse


def test_graph_event_hub_formats_sse_snapshot(tmp_path: Path, monkeypatch) -> None:
    async def run() -> str:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "cleaned").mkdir(parents=True)
        event = await GraphEventHub().snapshot_event(event_type="graph_snapshot", trigger="unit_test", limit=8)
        return format_sse("graph_snapshot", event)

    frame = asyncio.run(run())

    assert "event: graph_snapshot" in frame
    assert "data: " in frame
    assert "\"stream\":\"sse_v1\"" in frame


def test_cleaned_directory_watcher_triggers_memory_build_delta(tmp_path: Path) -> None:
    async def run() -> None:
        cleaned = tmp_path / "data" / "cleaned"
        ontology = tmp_path / "data" / "ontology"
        memory = tmp_path / "data" / "memory"
        cleaned.mkdir(parents=True)
        ontology.mkdir(parents=True)
        (ontology / "nodes.json").write_text("[]", encoding="utf-8")
        (ontology / "edges.json").write_text("[]", encoding="utf-8")
        (cleaned / "stream.md").write_text(
            "Real-time ingestion mints GhostTopology hashes. PayloadVault keeps text on local disk.",
            encoding="utf-8",
        )
        hub = GraphEventHub()
        watcher = CleanedDirectoryWatcher(
            hub=hub,
            cleaned_dir=str(cleaned),
            ontology_dir=str(ontology),
            memory_dir=str(memory),
        )
        subscriber_id, queue = await hub.subscribe(limit=64)
        try:
            await watcher.trigger_build(reason="unit_test", changed_paths=[str(cleaned / "stream.md")])
            events = [await asyncio.wait_for(queue.get(), timeout=2) for _ in range(3)]
        finally:
            await hub.unsubscribe(subscriber_id)

        assert any(event.get("event_type") == "graph_build_started" for event in events)
        delta = next(event for event in events if event.get("event_type") == "graph_delta")
        assert delta["graph_counts"]["nodes"] > 0
        assert delta["graph_counts"]["new_nodes"] > 0
        assert delta["new_node_ids"]
        assert "text/event-stream" not in format_sse("graph_delta", delta)

    asyncio.run(run())
