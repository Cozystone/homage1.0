from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.logical_sphere_summary import build_logical_sphere_summary


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_verified_counts_are_separated_from_candidate_counts(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(
        verified / "manifest.json",
        {
            "store_id": "cloud_brain_verified_store_v0",
            "counts": {"concepts": 7, "relations": 11, "evidence": 13, "case_frames": 17},
        },
    )
    candidate = tmp_path / "candidate"
    _write_json(
        candidate / "manifest.json",
        {
            "store_id": "cloud_brain_verified_store_v0_candidate",
            "counts": {"concepts": 3, "relations": 5, "evidence": 8, "case_frames": 2},
        },
    )

    summary = build_logical_sphere_summary(verified_store=verified, candidate_store_path=candidate).to_dict()

    assert summary["verified"]["verified_concepts"] == 7
    assert summary["verified"]["verified_relations"] == 11
    assert summary["verified"]["verified_evidence"] == 13
    assert summary["verified"]["verified_case_frames"] == 17
    assert summary["candidate"]["candidate_concepts"] == 3
    assert summary["candidate"]["candidate_relations"] == 5
    assert summary["candidate"]["candidate_evidence"] == 8
    assert summary["candidate"]["candidate_case_frames"] == 2
    assert summary["candidate"]["candidate_is_verified"] is False
    assert summary["candidate"]["source_status"] == "unpromoted_candidate_store"


def test_candidate_counts_fall_back_to_bounded_jsonl_without_promotion(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {"concepts": 1, "relations": 1}})
    candidate = tmp_path / "candidate_without_manifest"
    _write_jsonl(candidate / "concepts.jsonl", [{"concept_id": "a"}, {"concept_id": "b"}])
    _write_jsonl(candidate / "relations.jsonl", [{"relation_id": "r1"}])
    _write_jsonl(candidate / "evidence.jsonl", [{"evidence_id": "e1"}])
    _write_jsonl(candidate / "case_frames.jsonl", [{"frame_id": "f1"}, {"frame_id": "f2"}])

    summary = build_logical_sphere_summary(verified_store=verified, candidate_store_path=candidate).to_dict()

    assert summary["candidate"]["candidate_concepts"] == 2
    assert summary["candidate"]["candidate_relations"] == 1
    assert summary["candidate"]["candidate_evidence"] == 1
    assert summary["candidate"]["candidate_case_frames"] == 2
    assert summary["candidate"]["candidate_surface_items"] == 2
    assert summary["candidate"]["candidate_cgsr_items"] == 2
    assert summary["candidate"]["candidate_rhfc_items"] == 2
    assert summary["invariants"]["candidate_promotion"] is False
    assert not (candidate / "promoted.jsonl").exists()


def test_missing_candidate_store_is_zero_and_labeled(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {"concepts": 4}})

    summary = build_logical_sphere_summary(
        verified_store=verified,
        candidate_store_path=tmp_path / "missing_candidate",
    ).to_dict()

    assert summary["candidate"]["candidate_concepts"] == 0
    assert summary["candidate"]["candidate_relations"] == 0
    assert summary["candidate"]["source"] is None
    assert summary["candidate"]["source_status"] == "explicit_candidate_store_missing"
    assert summary["candidate"]["candidate_is_verified"] is False


def test_working_memory_counts_are_temporary_and_unknown_by_default(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {}})

    summary = build_logical_sphere_summary(verified_store=verified, candidate_store_path=tmp_path / "none").to_dict()

    assert summary["working_memory"]["working_memory_nodes"] is None
    assert summary["working_memory"]["working_memory_relations"] is None
    assert summary["working_memory"]["working_memory_fragments"] is None
    assert summary["working_memory"]["temporary"] is True
    assert summary["working_memory"]["source_status"] == "unknown_not_implemented"
    assert summary["explanations"]["working_memory_is_temporary"] is True


def test_rendered_counts_are_viewport_sample_not_total_graph(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {"concepts": 1000, "relations": 2000}})

    summary = build_logical_sphere_summary(
        verified_store=verified,
        candidate_store_path=tmp_path / "none",
        rendered_counts={
            "rendered_nodes": 120,
            "rendered_edges": 240,
            "materialized_nodes": 300,
            "materialized_edges": 450,
            "active_chunks": 12,
            "visible_scale_chunks": 32,
            "virtualization_enabled": True,
            "source": "test_viewport",
        },
    ).to_dict()

    assert summary["verified"]["verified_concepts"] == 1000
    assert summary["rendered"]["rendered_nodes"] == 120
    assert summary["rendered"]["rendered_edges"] == 240
    assert summary["rendered"]["materialized_nodes"] == 300
    assert summary["rendered"]["materialized_edges"] == 450
    assert summary["rendered"]["active_chunks"] == 12
    assert summary["rendered"]["visible_scale_chunks"] == 32
    assert summary["rendered"]["virtualization_enabled"] is True
    assert summary["explanations"]["rendered_counts_are_view_budget_not_total_graph"] is True


def test_missing_rendered_viewport_is_unknown_not_fake_total(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {"concepts": 1000, "relations": 2000}})

    summary = build_logical_sphere_summary(verified_store=verified, candidate_store_path=tmp_path / "none").to_dict()

    assert summary["rendered"]["rendered_nodes"] is None
    assert summary["rendered"]["rendered_edges"] is None
    assert summary["rendered"]["materialized_nodes"] is None
    assert summary["rendered"]["materialized_edges"] is None
    assert summary["rendered"]["source_status"] == "unknown_ui_owned"


def test_explanations_and_safety_invariants_are_explicit(tmp_path: Path) -> None:
    verified = tmp_path / "verified_store_v0"
    _write_json(verified / "manifest.json", {"counts": {}})

    summary = build_logical_sphere_summary(verified_store=verified, candidate_store_path=tmp_path / "none").to_dict()

    assert summary["explanations"] == {
        "verified_counts_change_only_after_promotion": True,
        "candidate_counts_are_unpromoted_learning": True,
        "rendered_counts_are_view_budget_not_total_graph": True,
        "working_memory_is_temporary": True,
        "local_brain_write_default": False,
    }
    assert summary["invariants"] == {
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "external_llm_used": False,
        "mock_growth": False,
        "real_p2p_used": False,
        "generated_code_executed": False,
    }
