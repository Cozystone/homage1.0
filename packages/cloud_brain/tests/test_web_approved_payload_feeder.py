from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

from packages.cloud_brain.bounded_learning_runner import BoundedLearningRunConfig, run_bounded_candidate_learning
from packages.cloud_brain.verified_payload_feeder import VerifiedPayloadFeeder
from packages.cloud_brain.web_approved_payload_feeder import (
    SourceSpec,
    WebFeederPolicy,
    collect_approved_payloads,
)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_approved_web_feeder_reports_no_configured_source_without_fabricating_payloads(tmp_path: Path) -> None:
    result = collect_approved_payloads([], output_dir=tmp_path / "approved")
    assert result.state == "no_configured_public_source"
    assert result.payloads_approved == 0
    assert result.duplicate_count == 0
    assert result.production_store_mutated is False
    assert result.external_llm_used is False
    assert result.mock_growth is False


def test_local_public_corpus_creates_policy_safe_payload_jsonl(tmp_path: Path) -> None:
    corpus = tmp_path / "public_corpus.txt"
    corpus.write_text(
        "지식 그래프는 개념과 관계를 표현합니다. "
        "그래프 데이터베이스는 노드와 관계를 저장합니다. "
        "AtanorSeedConcept123 sector 7 is a blocked mock template.",
        encoding="utf-8",
    )
    result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="local_public_corpus_file",
                source_id="fixture:public-corpus",
                source_url_or_path=str(corpus),
                license_hint="CC BY-SA 4.0 test fixture",
            )
        ],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )
    assert result.state == "payloads_approved"
    assert result.payloads_approved == 2
    assert result.payloads_rejected == 1
    assert result.approved_payload_path is not None
    rows = _read_jsonl(Path(result.approved_payload_path))
    assert {row["source_type"] for row in rows} == {"local_public_corpus_file"}
    assert all(row["target_store"] == "verified_store_v0_candidate" for row in rows)
    assert all(row["raw_text_hash"] for row in rows)
    assert all(row["normalized_text_hash"] for row in rows)
    assert all(row["provenance_hash"] for row in rows)
    assert all(row["collector"] == "atanor_web_feeder" for row in rows)
    assert all(row["collector_version"] == "approved_web_feeder_v1" for row in rows)
    assert all(row["is_mock"] is False for row in rows)
    assert all(row["is_private"] is False for row in rows)
    assert all(row["is_generated"] is False for row in rows)
    assert all(row["is_eval_row"] is False for row in rows)
    assert "mock_template_signal" in ",".join(result.rejection_reasons)
    assert Path(result.manifest_path or "").exists()


def test_local_public_corpus_shard_jsonl_creates_line_scoped_payloads(tmp_path: Path) -> None:
    shard = tmp_path / "public_shard.jsonl"
    rows = [
        {
            "text": "Public corpus shards provide provenance for candidate learning.",
            "title": "Public shard A",
            "source_url": "https://example.org/public/a",
            "license": "CC BY-SA 4.0",
            "language": "en",
        },
        {
            "text": "Public corpus shards provide provenance for candidate learning.",
            "title": "Public shard A duplicate",
            "source_url": "https://example.org/public/a-duplicate",
            "license": "CC BY-SA 4.0",
            "language": "en",
        },
        {
            "text": "AtanorSeedConcept42 sector 9 is forbidden mock material.",
            "title": "Mock row",
            "source_url": "https://example.org/public/mock",
            "license": "CC BY-SA 4.0",
            "language": "en",
        },
    ]
    shard.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="local_public_corpus_shard",
                source_id="fixture:public-shard",
                source_url_or_path=str(shard),
                license_hint="CC BY-SA 4.0",
            )
        ],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )

    assert result.source_mode == "local_dump_shard"
    assert result.payloads_approved == 1
    assert result.payloads_rejected == 2
    assert result.duplicate_count == 1
    assert result.rate_limited_count == 0
    assert result.recommended_source_for_long_run == "local_dump_shard"
    rows = _read_jsonl(Path(result.approved_payload_path or ""))
    assert rows[0]["source_type"] == "local_public_corpus_shard"
    assert rows[0]["source_id"].endswith(":line:1")
    assert rows[0]["source_url_or_path"] == "https://example.org/public/a"


def test_missing_local_public_corpus_shard_is_rejected(tmp_path: Path) -> None:
    result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="local_public_corpus_shard",
                source_id="fixture:missing-shard",
                source_url_or_path=str(tmp_path / "missing.jsonl"),
                license_hint="CC BY-SA 4.0",
            )
        ],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )
    assert result.payloads_approved == 0
    assert result.payloads_rejected == 1
    assert "source_file_missing" in result.rejection_reasons


def test_rest_429_backoff_is_recorded_without_crashing(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    class _Response:
        headers = {"content-type": "text/plain"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _limit: int) -> bytes:
            return b"Public evidence supports candidate graph learning."

    def _fake_urlopen(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError("https://en.wikipedia.org/wiki/Test", 429, "Too Many Requests", {}, None)
        return _Response()

    monkeypatch.setattr("packages.cloud_brain.web_approved_payload_feeder.urlopen", _fake_urlopen)
    monkeypatch.setattr("packages.cloud_brain.web_approved_payload_feeder.time.sleep", lambda _seconds: None)

    result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="public_web_feed",
                source_id="fixture:429",
                source_url_or_path="https://en.wikipedia.org/wiki/Test",
                license_hint="CC BY-SA 4.0",
            )
        ],
        policy=WebFeederPolicy(rest_max_retries=1, rest_backoff_base_seconds=0.01),
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )
    assert result.payloads_approved == 1
    assert result.rate_limited_count == 1
    assert result.backoff_seconds > 0
    assert result.last_429_at


def test_quality_gate_rejects_private_generated_eval_mojibake_and_duplicates(tmp_path: Path) -> None:
    source = SourceSpec(
        source_type="manual_public_sentence",
        source_id="fixture:manual",
        source_url_or_path="manual://approved-public-fixture",
        license_hint="CC BY-SA 4.0 test fixture",
        text=(
            "Retrieval systems use public evidence to ground answer generation. "
            "Retrieval systems use public evidence to ground answer generation. "
            "荑좊쾭?ㅽ떚?ㅻ뒗 而⑦뀒?대꼫瑜?愿由ы빀?덈떎. "
            "AtanorSeedConcept999 sector 9 should never become learning material."
        ),
    )
    result = collect_approved_payloads(
        [source],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )
    assert result.payloads_approved == 1
    assert result.payloads_rejected == 3
    assert result.duplicate_count == 1
    reasons = ",".join(result.rejection_reasons)
    assert "duplicate_payload" in reasons
    assert "mojibake_detected" in reasons
    assert "mock_template_signal" in reasons


def test_generated_payloads_feed_bounded_candidate_learning_without_production_mutation(tmp_path: Path) -> None:
    # consensus now counts VOICES (independent sources), so the re-confirming
    # sentence must come from a SECOND corpus file — one file is one voice.
    corpus = tmp_path / "public_corpus.txt"
    corpus.write_text(
        "의미 검색은 질문과 공개 근거를 연결합니다. "
        "지식 그래프는 개념과 관계와 출처 근거를 저장합니다.",
        encoding="utf-8",
    )
    corpus_b = tmp_path / "public_corpus_b.txt"
    corpus_b.write_text("지식 그래프는 모든 개념과 출처 근거를 저장합니다.", encoding="utf-8")
    feeder_result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="local_public_corpus_file",
                source_id="fixture:candidate-run",
                source_url_or_path=str(corpus),
                license_hint="CC BY-SA 4.0 test fixture",
            ),
            SourceSpec(
                source_type="local_public_corpus_file",
                source_id="fixture:candidate-run-b",
                source_url_or_path=str(corpus_b),
                license_hint="CC BY-SA 4.0 test fixture",
            ),
        ],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
        max_sentences=10,
    )
    assert feeder_result.approved_payload_path is not None
    approved_feeder = VerifiedPayloadFeeder(
        source_paths=[feeder_result.approved_payload_path],
        source_dir=tmp_path / "unused_default_dir",
        max_payloads_per_tick=10,
        max_payloads_per_run=10,
    )
    run_result = run_bounded_candidate_learning(
        BoundedLearningRunConfig(
            profile="interactive_safe",
            max_payloads=10,
            max_seconds=60,
            max_store_mb=64.0,
            min_ram_free_gb=0.0,
            min_disk_free_gb=0.0,
            max_cpu_percent=None,
            max_candidate_files=None,
            target_candidate_store=str(tmp_path / "candidate_store"),
            dry_run=False,
            execute=True,
            batch_size=5,
        ),
        feeder=approved_feeder,
    )
    assert run_result.state == "completed"
    assert run_result.payloads_accepted == 3
    assert run_result.concepts_added_candidate > 0
    assert run_result.relations_added_candidate > 0  # promoted via 2-source consensus
    assert run_result.surface_candidates > 0
    assert run_result.rhfc_candidates > 0
    assert run_result.production_store_mutated is False
    assert run_result.local_brain_write is False
    assert run_result.false_confident == 0
    assert run_result.forgetting_count == 0
    assert run_result.invariants["eval_rows_used_for_learning"] is False
    assert run_result.invariants["external_llm_used_for_reasoning"] is False
    assert run_result.invariants["mock_growth"] is False
    assert run_result.invariants["pair_edges_sent"] == 0


def test_dry_run_writes_no_payload_files(tmp_path: Path) -> None:
    source = SourceSpec(
        source_type="manual_public_sentence",
        source_id="fixture:dry-run",
        source_url_or_path="manual://approved-public-fixture",
        license_hint="CC BY-SA 4.0 test fixture",
        text="지식 그래프는 개념과 관계를 표현합니다.",
    )
    result = collect_approved_payloads(
        [source],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=True,
        max_sentences=10,
    )
    assert result.state == "payloads_approved"
    assert result.payloads_approved == 1
    assert result.approved_payload_path is None
    assert not (tmp_path / "approved").exists()
    assert not (tmp_path / "rejected").exists()
    assert not (tmp_path / "manifest.json").exists()


def test_missing_provenance_and_explicit_mock_rows_are_rejected_by_verified_feeder(tmp_path: Path) -> None:
    source = tmp_path / "payloads.jsonl"
    rows = [
        {
            "source_type": "manual_public_sentence",
            "source_id": "",
            "source_url_or_path": "",
            "text": "지식 그래프는 개념과 관계를 표현합니다.",
            "language": "ko",
            "license_hint": "CC BY-SA 4.0",
            "provenance_hash": "",
        },
        {
            "source_type": "manual_public_sentence",
            "source_id": "mock-flag",
            "source_url_or_path": "manual://mock-flag",
            "text": "지식 그래프는 개념과 관계를 표현합니다.",
            "language": "ko",
            "license_hint": "CC BY-SA 4.0",
            "provenance_hash": "mock-provenance",
            "is_mock": True,
        },
    ]
    source.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    feeder = VerifiedPayloadFeeder(source_paths=[source], source_dir=tmp_path / "unused_default_dir")
    result = feeder.run_once()
    assert result.payloads_accepted == 0
    assert result.payloads_rejected == 2
    assert "missing_provenance" in result.last_rejection_reasons
    assert "mock_payload_rejected" in result.last_rejection_reasons
