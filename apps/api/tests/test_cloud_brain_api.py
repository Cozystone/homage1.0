from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.services.brain_graph_state import build_brain_graph_states
from app.services.hybrid_network_manager import GraphFragmentEnvelope


client = TestClient(app)


def test_cloud_brain_status_is_local_facade() -> None:
    response = client.get("/api/cloud-brain/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Cloud Brain"
    assert payload["mode"] == "shared-public-ontology-control-plane"
    assert payload["public_cloud_backend_enabled"] is False
    assert payload["answer_policy"]["external_llm"] is False
    assert payload["cloud_graph_state"]["schema"] == "atanor.cloud-brain-graph-state.v1"
    assert payload["local_graph_state"]["schema"] == "atanor.local-brain-graph-state.v1"
    assert payload["cloud_graph_state"]["fake_growth_counters"] is False
    assert payload["data_source_audit"]["uses_fallback_sample_graph"] is False
    assert isinstance(payload["web_feeder_state"]["enabled"], bool)
    assert payload["web_feeder_state"]["writes_local_brain"] is False
    assert payload["web_feeder_state"]["privacy_scope"] == "public_cloud_candidates_only"


def test_cloud_brain_query_returns_fragments_without_external_llm() -> None:
    response = client.post("/api/cloud-brain/query", json={"query": "GraphRAG memory"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local_cloud_brain_facade"
    assert payload["promotion_policy"]["writes_public_cloud"] is False
    assert "active_nodes" in payload["fragments"]


def test_semantic_graph_endpoint_uses_read_model_flags() -> None:
    response = client.get("/api/cloud-brain/semantic/graph?limit_nodes=16&limit_edges=32")

    assert response.status_code == 200
    payload = response.json()
    assert payload["proof_store_only"] is True
    assert payload["old_mirror_snapshot_used"] is False
    assert payload["performance"]["full_store_scan"] is False
    assert payload["performance"]["index_rebuild_during_request"] is False


def test_cloud_brain_ingest_appends_public_fragment_to_local_broker(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    response = client.post(
        "/api/cloud-brain/ingest",
        json={
            "source_url": "https://example.com",
            "text": "Cloud Brain public fragment validates GraphRAG evidence routing and Payload Vault storage.",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["state"] == "accepted"
    assert payload["fragment_store"] == "local_companion_payload_vault"
    assert payload["fragment"]["raw_fragment_path"].endswith(".md")


def test_cloud_brain_fragment_endpoint_returns_valid_hash_topology(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ingest = client.post(
        "/api/cloud-brain/ingest",
        json={
            "source_url": "local://fragment-test",
            "text": "GraphRAG evidence routing activates Ghost Shell hashes and Payload Vault WAL storage for Cloud Brain fragments.",
            "dry_run": False,
        },
    )
    assert ingest.status_code == 200

    response = client.get("/api/cloud-brain/fragment", params={"concept_id": "GraphRAG", "peer_id": "atanor-local-peer"})

    assert response.status_code == 200
    payload = response.json()
    envelope = GraphFragmentEnvelope.from_mapping(payload)
    envelope.validate()
    assert payload["transport"]["raw_payload_exported"] is False
    assert payload["nodes"]
    assert "raw_text" not in payload["nodes"][0]


def test_anna_archive_metadata_search_can_ingest_metadata_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_fetch_metadata(query: str) -> dict:
        return {
            "enabled": True,
            "configured": True,
            "status": "metadata_fetched",
            "records": [
                {
                    "source_id": "anna_meta_graph_rag",
                    "source_hash": "hash_graph_rag",
                    "title": "GraphRAG and Knowledge Graph Retrieval",
                    "authors": ["A. Researcher"],
                    "year": "2026",
                    "language": "en",
                    "license": "metadata-only",
                    "source_url": "https://example.test/metadata/graph-rag",
                    "query": query,
                    "privacy_scope": "public_metadata",
                    "raw_text_stored": False,
                    "download_url_stored": False,
                    "usage_allowed": False,
                }
            ],
            "rejected": 0,
            "honesty": {"metadata_only": True, "full_text_downloads": False, "local_brain_write": False},
        }

    monkeypatch.setattr("app.routers.cloud_brain.fetch_anna_archive_metadata", fake_fetch_metadata)

    response = client.post(
        "/api/cloud-brain/anna-archive/search",
        json={"query": "GraphRAG knowledge graph", "ingest": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "metadata_fetched"
    assert payload["semantic_ingest"]["requested"] is True
    assert payload["semantic_ingest"]["records_ingested"] == 1
    assert payload["semantic_ingest"]["local_brain_write"] is False
    assert payload["semantic_ingest"]["raw_text_storage"] is False
    assert payload["semantic_ingest"]["download_url_storage"] is False
    assert payload["policy"]["full_text_downloads"] is False

    status = client.get("/api/cloud-brain/semantic/status").json()
    assert status["concepts"] > 0
    assert status["old_mirror_snapshot_used_as_live_cloud"] is False


def test_cloud_and_local_graph_states_are_separated_with_growth_fields(tmp_path) -> None:
    db_path = tmp_path / "data" / "memory" / "homage.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    now = datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.executescript(
        """
        CREATE TABLE ghost_nodes(node_hash TEXT PRIMARY KEY);
        CREATE TABLE ghost_edges(source_hash TEXT, target_hash TEXT);
        CREATE TABLE payload_vault(hash_key TEXT PRIMARY KEY);
        CREATE TABLE nodes(node_id TEXT PRIMARY KEY);
        CREATE TABLE edges(edge_id TEXT PRIMARY KEY);
        CREATE TABLE memory_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, subject_id TEXT, payload_json TEXT, created_at TEXT);
        CREATE TABLE ingested_files(file_fingerprint TEXT PRIMARY KEY, original_path TEXT, cleaned_path TEXT, byte_count INTEGER, node_count INTEGER, edge_count INTEGER, status TEXT, ingested_at TEXT);
        CREATE TABLE learning_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, subject_id TEXT, payload_json TEXT, created_at TEXT);
        """
    )
    conn.executemany("INSERT INTO ghost_nodes(node_hash) VALUES (?)", [("g1",), ("g2",), ("g3",)])
    conn.executemany("INSERT INTO ghost_edges(source_hash, target_hash) VALUES (?, ?)", [("g1", "g2"), ("g2", "g3")])
    conn.executemany("INSERT INTO payload_vault(hash_key) VALUES (?)", [("p1",), ("p2",), ("p3",)])
    conn.executemany("INSERT INTO nodes(node_id) VALUES (?)", [("n1",), ("n2",), ("n3",), ("n4",)])
    conn.executemany("INSERT INTO edges(edge_id) VALUES (?)", [("e1",), ("e2",), ("e3",), ("e4",), ("e5",)])
    conn.execute("INSERT INTO memory_events(event_type, subject_id, payload_json, created_at) VALUES ('node_imported','g3','{}',?)", (recent,))
    conn.execute("INSERT INTO memory_events(event_type, subject_id, payload_json, created_at) VALUES ('edge_imported','g2:g3','{}',?)", (recent,))
    conn.execute("INSERT INTO memory_events(event_type, subject_id, payload_json, created_at) VALUES ('document_imported','d1','{}',?)", (old,))
    conn.execute(
        "INSERT INTO ingested_files(file_fingerprint, original_path, cleaned_path, byte_count, node_count, edge_count, status, ingested_at) VALUES ('f1','raw','clean',10,1,1,'ingested',?)",
        (recent,),
    )
    conn.commit()
    conn.close()

    states = build_brain_graph_states(
        daemon={"worker_alive": True, "desired_running": True, "queue_state": "PERSISTENT_APPEND_APPLIED", "state": "running"},
        memory={"db_path": str(db_path), "built_at": old, "event_count": 3},
        now=now,
    )

    cloud = states["cloud"]
    local = states["local"]
    assert cloud["cloud_total_nodes"] == 3
    assert cloud["cloud_total_relations"] == 2
    assert cloud["cloud_nodes_added_recently"] == 1
    assert cloud["cloud_relations_added_recently"] == 1
    assert cloud["cloud_fragments_merged_recently"] == 1
    assert cloud["fake_growth_counters"] is False
    assert cloud["is_growing"] is True
    assert local["local_brain_initialized"] is False
    assert local["local_brain_empty"] is True
    assert local["local_total_nodes"] == 0
    assert local["local_total_relations"] == 0
    assert local["cloud_mirror_nodes_excluded"] == 3
    assert local["cloud_mirror_relations_excluded"] == 2
    assert states["audit"]["uses_fallback_sample_graph"] is False


def test_cloud_graph_state_detects_stale_snapshot(tmp_path) -> None:
    db_path = tmp_path / "data" / "memory" / "homage.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    old = "2026-06-14T06:00:00Z"
    conn.executescript(
        """
        CREATE TABLE ghost_nodes(node_hash TEXT PRIMARY KEY);
        CREATE TABLE ghost_edges(source_hash TEXT, target_hash TEXT);
        CREATE TABLE payload_vault(hash_key TEXT PRIMARY KEY);
        CREATE TABLE nodes(node_id TEXT PRIMARY KEY);
        CREATE TABLE edges(edge_id TEXT PRIMARY KEY);
        CREATE TABLE memory_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, subject_id TEXT, payload_json TEXT, created_at TEXT);
        CREATE TABLE ingested_files(file_fingerprint TEXT PRIMARY KEY, original_path TEXT, cleaned_path TEXT, byte_count INTEGER, node_count INTEGER, edge_count INTEGER, status TEXT, ingested_at TEXT);
        CREATE TABLE learning_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, subject_id TEXT, payload_json TEXT, created_at TEXT);
        """
    )
    conn.executemany("INSERT INTO ghost_nodes(node_hash) VALUES (?)", [("g1",), ("g2",)])
    conn.execute("INSERT INTO ghost_edges(source_hash, target_hash) VALUES ('g1', 'g2')")
    conn.execute("INSERT INTO memory_events(event_type, subject_id, payload_json, created_at) VALUES ('node_imported','g1','{}',?)", (old,))
    conn.commit()
    conn.close()

    states = build_brain_graph_states(
        daemon={"worker_alive": True, "desired_running": True, "queue_state": "WAITING_FOR_PAYLOADS", "state": "running"},
        memory={"db_path": str(db_path), "built_at": old, "event_count": 1},
        now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
    )

    cloud = states["cloud"]
    assert cloud["cloud_nodes_added_recently"] == 0
    assert cloud["is_growing"] is False
    assert cloud["is_stale"] is True
    assert cloud["ingest_status"] == "listening"
