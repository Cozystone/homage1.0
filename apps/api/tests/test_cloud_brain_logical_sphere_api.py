"""Logical Sphere summary endpoint — the four count domains (verified / candidate /
working-memory / rendered) must arrive SEPARATED, flagged, and read-only, so a viewport
sample or unpromoted learning can never be presented as production graph size."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_logical_sphere_summary_separates_the_four_domains() -> None:
    res = client.get("/api/cloud-brain/logical-sphere/summary")
    assert res.status_code == 200
    body = res.json()
    # the four domains exist and are distinct objects, never merged into one total
    for domain in ("verified", "candidate", "working_memory", "rendered"):
        assert isinstance(body.get(domain), dict), domain
    assert "verified_concepts" in body["verified"]
    assert "candidate_concepts" in body["candidate"]
    assert body["candidate"]["candidate_is_verified"] is False
    # working memory is temporary and, unowned by this backend, reported unknown — not invented
    assert body["working_memory"]["temporary"] is True
    # rendered counts are UI-owned; the backend must not fabricate them
    assert body["rendered"]["source_status"] in ("unknown_ui_owned", "provided_viewport_sample")


def test_logical_sphere_summary_carries_explanations_and_invariants() -> None:
    body = client.get("/api/cloud-brain/logical-sphere/summary").json()
    exp = body["explanations"]
    assert exp["verified_counts_change_only_after_promotion"] is True
    assert exp["candidate_counts_are_unpromoted_learning"] is True
    assert exp["rendered_counts_are_view_budget_not_total_graph"] is True
    inv = body["invariants"]
    assert inv["production_store_mutated"] is False
    assert inv["candidate_promotion"] is False
    assert inv["external_llm_used"] is False


def test_logical_sphere_summary_is_read_only_and_repeatable() -> None:
    first = client.get("/api/cloud-brain/logical-sphere/summary").json()
    second = client.get("/api/cloud-brain/logical-sphere/summary").json()
    # a status read must not change any count (no scan-triggered growth, no promotion)
    assert first["verified"] == second["verified"]
    assert first["candidate"] == second["candidate"]
