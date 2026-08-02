"""PipelineRunner end-to-end + determinism on the fixture corpus."""

from __future__ import annotations

import json
from pathlib import Path

from datagate import DataGateConfig, PipelineRunner


def _read_jsonl(config: DataGateConfig) -> list[dict]:
    path = Path(config.metadata_dir) / "documents.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_partition_invariant(corpus: DataGateConfig):
    report = PipelineRunner(corpus).run()
    assert report.state == "completed"
    assert report.accepted + report.rejected == report.total
    assert report.total == 8  # one file per scenario


def test_every_doc_in_jsonl(corpus: DataGateConfig):
    report = PipelineRunner(corpus).run()
    records = _read_jsonl(corpus)
    assert len(records) == report.total


def test_rejected_have_reason_and_rejected_by(corpus: DataGateConfig):
    PipelineRunner(corpus).run()
    for rec in _read_jsonl(corpus):
        if rec["status"] == "rejected":
            assert rec["rejection_reason"]
            assert rec["rejected_by"]
        else:
            assert rec["quality_score"] is not None


def test_accepted_have_cleaned_file(corpus: DataGateConfig):
    PipelineRunner(corpus).run()
    cleaned = Path(corpus.cleaned_dir)
    for rec in _read_jsonl(corpus):
        if rec["status"] == "accepted":
            assert (cleaned / f"{rec['doc_id']}.txt").exists()


def test_expected_rejections(corpus: DataGateConfig):
    report = PipelineRunner(corpus).run()
    breakdown = report.rejection_breakdown
    # short.txt + empty.txt are both too short
    assert breakdown.get("min_length", 0) >= 2
    # dup_b.txt duplicates dup_a.txt (and the clean_long doc shares content)
    assert breakdown.get("duplicate_hash", 0) >= 1
    assert breakdown.get("special_char_ratio", 0) >= 1
    assert breakdown.get("link_density", 0) >= 1


def test_duplicate_reason_references_first(corpus: DataGateConfig):
    PipelineRunner(corpus).run()
    dup = [r for r in _read_jsonl(corpus) if r["rejected_by"] == "duplicate_hash"]
    assert dup
    for rec in dup:
        assert "duplicate of doc_id" in rec["rejection_reason"]


def test_determinism_two_runs(corpus: DataGateConfig):
    report1 = PipelineRunner(corpus).run()
    records1 = _read_jsonl(corpus)
    cleaned1 = sorted(p.name for p in Path(corpus.cleaned_dir).iterdir())
    rejected1 = sorted(p.name for p in Path(corpus.rejected_dir).iterdir())

    report2 = PipelineRunner(corpus).run()
    records2 = _read_jsonl(corpus)
    cleaned2 = sorted(p.name for p in Path(corpus.cleaned_dir).iterdir())
    rejected2 = sorted(p.name for p in Path(corpus.rejected_dir).iterdir())

    # Identical file partitions
    assert cleaned1 == cleaned2
    assert rejected1 == rejected2
    # Identical counts
    assert (report1.total, report1.accepted, report1.rejected) == (
        report2.total,
        report2.accepted,
        report2.rejected,
    )
    # Identical jsonl except run_id / processed_at
    volatile = {"run_id", "processed_at"}
    for r1, r2 in zip(records1, records2):
        assert {k: v for k, v in r1.items() if k not in volatile} == {
            k: v for k, v in r2.items() if k not in volatile
        }


def test_read_error_becomes_rejection(config: DataGateConfig):
    raw = Path(config.input_dir)
    raw.mkdir(parents=True, exist_ok=True)
    # Invalid UTF-8 bytes -> UnicodeDecodeError on read
    (raw / "broken.txt").write_bytes(b"\xff\xfe\x00\x80broken\xff")

    report = PipelineRunner(config).run()
    assert report.state == "completed"
    assert report.total == 1
    assert report.rejected == 1
    rec = _read_jsonl(config)[0]
    assert rec["status"] == "rejected"
    assert rec["rejected_by"] == "read_error"
    assert rec["rejection_reason"].startswith("read_error:")


def test_empty_raw_dir_completes(config: DataGateConfig):
    report = PipelineRunner(config).run()
    assert report.state == "completed"
    assert report.total == 0
    assert report.accepted == 0
    assert report.rejected == 0
    # input dir is created if missing
    assert Path(config.input_dir).exists()


def test_doc_ids_stable_across_runs(corpus: DataGateConfig):
    PipelineRunner(corpus).run()
    ids1 = sorted(r["doc_id"] for r in _read_jsonl(corpus))
    PipelineRunner(corpus).run()
    ids2 = sorted(r["doc_id"] for r in _read_jsonl(corpus))
    assert ids1 == ids2
