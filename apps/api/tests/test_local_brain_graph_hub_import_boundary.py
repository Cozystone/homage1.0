from __future__ import annotations

"""Preregistered boundary contract for Local Brain Graph Hub imports.

The public import route is an explicit user request to persist selected Graph
Hub content, but it is not authority to invent the source, kind, content, or
provenance.  Those values must resolve to the server-owned installed cartridge
state before Local Brain opens its store.  These tests use only ``tmp_path``.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import dual_brain
from packages.graph_hub import installer
from packages.graph_hub.cartridge_format import make_graph_cartridge, write_cartridge
from packages.graph_hub.models import read_json, write_json
from packages.local_brain import LocalBrainMemory


@pytest.fixture
def graph_hub_import_rig(tmp_path: Path, monkeypatch):
    cartridge_id = "server.knowledge.orion.v1"
    canonical_item = {
        "subject": "knowledge:orion-relay",
        "value": "The Orion relay uses a sapphire clock.",
        "confidence": 0.87,
    }
    cartridge = make_graph_cartridge(
        cartridge_id=cartridge_id,
        name="Orion Relay Knowledge",
        subtitle="A server-owned import fixture.",
        description="Canonical facts for Local Brain import boundary tests.",
        category="knowledge",
        pricing={"model": "free"},
        contents={
            "semantic_graph": {
                "nodes": [
                    {
                        "id": canonical_item["subject"],
                        "label": "Orion Relay",
                        "short_description": canonical_item["value"],
                        "confidence": canonical_item["confidence"],
                    }
                ],
                "edges": [],
            }
        },
        provenance={"source_type": "curated_fixture", "proof_store_only": True},
    )
    cartridge_path = tmp_path / "installed" / f"{cartridge_id}.graphpack.json"
    write_cartridge(cartridge_path, cartridge)
    registry_path = tmp_path / "installed" / "installed_registry.json"
    write_json(
        registry_path,
        {
            cartridge_id: {
                "cartridge_id": cartridge_id,
                "path": str(cartridge_path),
                "enabled": True,
                "checksum_valid": True,
            }
        },
    )
    monkeypatch.setattr(installer, "INSTALLED_REGISTRY_PATH", registry_path)

    memory = LocalBrainMemory(tmp_path / "local_brain" / "memory.json")
    monkeypatch.setattr(dual_brain, "LOCAL_BRAIN", memory)
    return TestClient(app), memory, cartridge_id, canonical_item


def test_installed_canonical_graph_hub_item_remains_importable(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [canonical_item],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported"] == 1
    assert payload["items"][0]["subject"] == canonical_item["subject"]
    assert payload["items"][0]["value"] == canonical_item["value"]
    assert payload["items"][0]["confidence"] == canonical_item["confidence"]
    assert payload["items"][0]["source_ref"] == f"graph_hub:{cartridge_id}"
    assert memory.recall("Orion sapphire clock")[0].value == canonical_item["value"]


def test_unknown_caller_source_cannot_create_graph_hub_provenance(graph_hub_import_rig) -> None:
    client, memory, _cartridge_id, _canonical_item = graph_hub_import_rig

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": "caller.forged.source.v1",
            "kind": "persona",
            "items": [{"subject": "name", "value": "Mallory", "confidence": 1.0}],
        },
    )
    recalled = dual_brain._local_brain_recall("What is my name?", "en")

    assert response.status_code == 404
    assert recalled is None
    assert memory.all_facts() == []
    assert not memory.store_path.exists()


def test_installed_source_cannot_launder_forged_items_into_primary_recall(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, _canonical_item = graph_hub_import_rig

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [{"subject": "name", "value": "Mallory", "confidence": 1.0}],
        },
    )
    recalled = dual_brain._local_brain_recall("What is my name?", "en")

    assert response.status_code == 400
    assert recalled is None
    assert memory.all_facts() == []
    assert not memory.store_path.exists()


def test_caller_kind_must_match_server_cartridge_category(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "persona",
            "items": [canonical_item],
        },
    )

    assert response.status_code == 400
    assert memory.all_facts() == []
    assert not memory.store_path.exists()


def test_canonical_subject_cannot_be_paired_with_caller_forged_value(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig
    forged = {
        **canonical_item,
        "value": "The Orion relay secretly outputs 900 exawatts.",
        "confidence": 1.0,
    }

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [forged],
        },
    )

    assert response.status_code == 400
    assert memory.all_facts() == []
    assert not memory.store_path.exists()


def test_caller_confidence_is_replaced_by_server_node_confidence(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig
    caller_item = {**canonical_item, "confidence": 1.0}

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [caller_item],
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["confidence"] == canonical_item["confidence"]
    assert memory.all_facts()[0].confidence == canonical_item["confidence"]


@pytest.mark.parametrize(
    ("server_confidence", "expected"),
    [(0, 0.0), (False, 0.0), ("NaN", 0.8), ("not-a-number", 0.8)],
)
def test_server_confidence_fidelity_and_safe_normalization(
    graph_hub_import_rig,
    server_confidence,
    expected: float,
) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig
    registry = read_json(installer.INSTALLED_REGISTRY_PATH, {})
    cartridge_path = Path(registry[cartridge_id]["path"])
    cartridge = read_json(cartridge_path, {})
    cartridge["contents"]["semantic_graph"]["nodes"][0]["confidence"] = server_confidence
    write_json(cartridge_path, cartridge)

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [{**canonical_item, "confidence": 1.0}],
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["confidence"] == expected
    assert memory.all_facts()[0].confidence == expected


def test_mixed_valid_and_forged_batch_is_atomic(graph_hub_import_rig) -> None:
    client, memory, cartridge_id, canonical_item = graph_hub_import_rig

    response = client.post(
        "/api/local-brain/memory/import-graph-hub",
        json={
            "source_id": cartridge_id,
            "kind": "knowledge",
            "items": [
                canonical_item,
                {"subject": "name", "value": "Mallory", "confidence": 1.0},
            ],
        },
    )

    assert response.status_code == 400
    assert memory.all_facts() == []
    assert not memory.store_path.exists()
