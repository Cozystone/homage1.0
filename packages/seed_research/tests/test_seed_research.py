from __future__ import annotations

import json
from pathlib import Path

from seed_research import apply_feedback, current_viewer_export, freeze_seed, run_seed_iteration


def test_seed_iteration_creates_artifacts_without_local_memory(tmp_path, monkeypatch) -> None:
    root = tmp_path / "seed_research"
    monkeypatch.chdir(tmp_path)

    result = run_seed_iteration(root)
    run_dir = Path(result["run_dir"])

    expected = [
        "seed_candidates.jsonl",
        "seed_concepts.jsonl",
        "seed_edges.jsonl",
        "seed_aliases.jsonl",
        "seed_metrics.json",
        "seed_eval_report.md",
        "human_feedback.md",
        "rejected_concepts.jsonl",
        "rejected_edges.jsonl",
        "graph_snapshot.json",
        "viewer_export.json",
    ]
    for name in expected:
        assert (run_dir / name).exists(), name

    assert (root / "relation_schema.json").exists()
    assert (root / "benchmarks" / "seed_benchmark_questions.jsonl").exists()
    assert (root / "current" / "viewer_export.json").exists()
    assert not (tmp_path / "data" / "memory").exists()

    metrics = json.loads((run_dir / "seed_metrics.json").read_text(encoding="utf-8"))
    assert metrics["concept_count"] > 8
    assert metrics["edge_count"] > 8
    assert metrics["duplicate_merge_count"] >= 1
    assert metrics["benchmark_score"] > 0.6
    assert metrics["benchmark_score"] >= 0.82

    viewer = json.loads((run_dir / "viewer_export.json").read_text(encoding="utf-8"))
    assert viewer["mode"] == "seed_research_viewer"
    assert viewer["read_only"] is True
    assert viewer["not_local_brain"] is True
    assert viewer["concept_count"] == metrics["concept_count"]
    labels = {node["id"]: node["labels"]["ko"] for node in viewer["nodes"]}
    assert labels["seed.core.evidence"] == "근거"
    assert labels["seed.core.no_evidence"] == "근거 없음"
    assert "�" not in json.dumps(viewer, ensure_ascii=False)


def test_previous_runs_are_immutable_and_current_updates(tmp_path) -> None:
    root = tmp_path / "seed_research"
    first = run_seed_iteration(root)
    run_1 = Path(first["run_dir"])
    before = (run_1 / "seed_metrics.json").read_text(encoding="utf-8")

    second = run_seed_iteration(root)

    assert Path(second["run_dir"]).name == "run_0002"
    assert (run_1 / "seed_metrics.json").read_text(encoding="utf-8") == before
    manifest = json.loads((root / "current" / "seed_manifest.json").read_text(encoding="utf-8"))
    assert manifest["current_run_id"] == "run_0002"


def test_feedback_patch_does_not_mutate_run(tmp_path) -> None:
    root = tmp_path / "seed_research"
    result = run_seed_iteration(root)
    run_dir = Path(result["run_dir"])
    before = (run_dir / "human_feedback.md").read_text(encoding="utf-8")
    patch = apply_feedback("run_0001", root)

    assert Path(patch["patch_path"]).exists()
    assert (run_dir / "human_feedback.md").read_text(encoding="utf-8") == before
    assert not (run_dir / "feedback_patch.json").exists()


def test_freeze_seed_creates_read_only_artifact(tmp_path) -> None:
    root = tmp_path / "seed_research"
    output = tmp_path / "seed"
    run_seed_iteration(root)
    frozen = freeze_seed("run_0001", "seed-core-0.1", root, output)

    assert Path(frozen["output_dir"]) == output
    for name in ["seed_manifest.json", "seed_concepts.jsonl", "seed_edges.jsonl", "seed_aliases.jsonl", "seed_eval_report.md"]:
        assert (output / name).exists(), name
    manifest = json.loads((output / "seed_manifest.json").read_text(encoding="utf-8"))
    assert manifest["read_only"] is True
    assert manifest["version"] == "seed-core-0.1"


def test_current_viewer_export_reads_only_seed_current(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)
    viewer = current_viewer_export(root)

    assert viewer["mode"] == "seed_research_viewer"
    assert viewer["not_local_brain"] is True
    assert viewer["nodes"]
    assert viewer["edges"]
