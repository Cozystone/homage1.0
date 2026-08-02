from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.continuous_learning import CloudSurfaceLearningLoop
from packages.cloud_brain.public_corpus_shard_builder import PublicCorpusBuilderConfig, build_public_corpus_shard
from packages.cloud_brain.verified_payload_feeder import payload_from_mapping


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_english_quality_gate_rejects_markup_navigation_urls_and_low_alpha(tmp_path: Path) -> None:
    source = tmp_path / "english.jsonl"
    _jsonl(
        source,
        [
            {
                "text": "Kubernetes manages containerized applications across distributed clusters.",
                "license": "CC BY-SA 4.0",
                "language": "en",
            },
            {"text": "{{Infobox}} This article needs additional citations.", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "| class = wikitable | broken table row", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "https://example.org/only-a-url", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "12345 ---- 67890 ////", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "Mojibake Ã¼ text should be rejected.", "license": "CC BY-SA 4.0", "language": "en"},
        ],
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="english-fixture",
            license_hint="CC BY-SA 4.0",
            language="en",
            dry_run=True,
            execute=False,
        )
    )

    assert result.rows_accepted == 1
    reasons = result.rejection_reasons
    assert "wikitext_residue" in reasons
    assert "maintenance_residue" in reasons
    assert "table_or_list_residue" in reasons
    assert "url_only" in reasons
    assert "low_alpha_ratio" in reasons
    assert "mojibake" in reasons


def test_korean_compatibility_accepts_korean_and_rejects_mojibake(tmp_path: Path) -> None:
    source = tmp_path / "korean.jsonl"
    _jsonl(
        source,
        [
            {
                "text": "쿠버네티스는 컨테이너를 관리하는 공개 문서 기반 시스템입니다.",
                "license": "CC BY-SA 4.0",
                "language": "ko",
            },
            {"text": "깨진 Ã¼ 문자열은 거부되어야 합니다.", "license": "CC BY-SA 4.0", "language": "ko"},
        ],
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="korean-fixture",
            license_hint="CC BY-SA 4.0",
            language="ko",
            min_chars=12,
            min_alpha_ratio=0.2,
            dry_run=True,
            execute=False,
        )
    )

    assert result.rows_accepted == 1
    assert result.rejection_reasons["mojibake"] == 1


def test_english_payload_reaches_candidate_learning_without_production_mutation(tmp_path: Path) -> None:
    source = tmp_path / "english.jsonl"
    _jsonl(
        source,
        [
            {
                "text": "Kubernetes manages containerized applications across distributed clusters.",
                "title": "Kubernetes",
                "source_url": "https://en.wikipedia.org/wiki/Kubernetes",
                "license": "CC BY-SA 4.0",
                "language": "en",
            }
        ],
    )
    built = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="english-fixture",
            license_hint="CC BY-SA 4.0",
            language="en",
            dry_run=True,
            execute=False,
        )
    )
    assert built.rows_accepted == 1
    payloads = [payload_from_mapping(row) for row in built.samples]

    loop = CloudSurfaceLearningLoop(candidate_store_root=tmp_path / "candidate")
    result = loop.run_once(payloads=payloads, max_accepted_per_run=1)

    assert result.active_learning_state == "learning"
    assert result.production_store_mutated is False
    assert result.semantic.local_brain_write is False
    assert result.false_confident == 0
    assert result.forgetting_count == 0
    assert result.pair_edges_sent == 0
    assert result.private_data_used_for_cloud_learning is False
    assert result.semantic.external_llm_used is False
    assert result.semantic.mock_growth is False
    assert result.semantic.eval_rows_used_for_learning is False
    assert result.semantic.concepts_added >= 2
    assert result.semantic.case_frames_added == 1
