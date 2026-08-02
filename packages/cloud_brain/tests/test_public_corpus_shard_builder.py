from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.public_corpus_shard_builder import (
    PublicCorpusBuilderConfig,
    build_public_corpus_shard,
)
from packages.cloud_brain.verified_payload_feeder import PayloadSourcePolicy, payload_from_mapping


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_dry_run_writes_no_payload_file(tmp_path: Path) -> None:
    source = tmp_path / "public.jsonl"
    _jsonl(
        source,
        [
            {
                "text": "Public corpus evidence supports candidate learning with traceable provenance.",
                "title": "A",
                "source_url": "https://example.org/a",
                "license": "CC BY-SA 4.0",
                "language": "en",
            }
        ],
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="fixture",
            license_hint="CC BY-SA 4.0",
            language="en",
            output_dir=str(tmp_path / "approved"),
            dry_run=True,
            execute=False,
        )
    )

    assert result.mode == "dry_run"
    assert result.rows_accepted == 1
    assert result.output_path is None
    assert not (tmp_path / "approved").exists()


def test_execute_writes_valid_approved_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "public.txt"
    source.write_text(
        "Public corpus shards provide approved evidence for candidate graph learning.\n"
        "Another public corpus sentence keeps source provenance and license metadata.\n",
        encoding="utf-8",
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="fixture",
            source_url="https://example.org/source",
            license_hint="CC BY-SA 4.0",
            language="en",
            output_dir=str(tmp_path / "approved"),
            audit_dir=str(tmp_path / "audit"),
            dry_run=False,
            execute=True,
        )
    )

    assert result.state == "payloads_approved"
    assert result.output_path is not None
    rows = [json.loads(line) for line in Path(result.output_path).read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert {row["source_type"] for row in rows} == {"local_public_corpus_shard"}
    assert {row["source_mode"] for row in rows} == {"local_dump_shard"}
    assert all(row["collector"] == "public_corpus_shard_builder" for row in rows)
    assert all(row["is_private"] is False for row in rows)
    assert all(row["is_generated"] is False for row in rows)
    assert all(row["is_eval_row"] is False for row in rows)
    assert all(row["is_mock"] is False for row in rows)
    policy = PayloadSourcePolicy()
    assert all(policy.decide(payload_from_mapping(row)).accepted for row in rows)


def test_builder_reads_local_wikipedia_xml_with_page_revision_fields(tmp_path: Path) -> None:
    source = tmp_path / "enwiki.xml"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<mediawiki>
  <page>
    <title>Graph theory</title>
    <ns>0</ns>
    <id>42</id>
    <revision>
      <id>84</id>
      <text>Graph theory describes relationships between mathematical objects. It provides public concepts for network analysis.</text>
    </revision>
  </page>
</mediawiki>
""",
        encoding="utf-8",
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="enwiki-fixture",
            license_hint="CC BY-SA 4.0",
            language="en",
            input_format="auto",
            dry_run=True,
            execute=False,
        )
    )

    assert result.rows_accepted == 2
    assert {row["page_id"] for row in result.samples} == {"42"}
    assert {row["revision_id"] for row in result.samples} == {"84"}
    assert {row["sentence_index"] for row in result.samples} == {1, 2}
    assert all(row["source_mode"] == "local_dump_shard" for row in result.samples)


def test_missing_source_file_is_rejected(tmp_path: Path) -> None:
    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(tmp_path / "missing.jsonl"),
            source_name="fixture",
            license_hint="CC BY-SA 4.0",
        )
    )

    assert result.state == "source_file_missing"
    assert result.rejection_reasons["source_file_missing"] == 1


def test_unknown_license_is_rejected_by_default(tmp_path: Path) -> None:
    source = tmp_path / "public.txt"
    source.write_text("A public-looking sentence without an approved license must not pass.\n", encoding="utf-8")

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="fixture",
            license_hint="unknown",
            language="en",
        )
    )

    assert result.state == "no_approved_rows"
    assert result.rejection_reasons["unknown_license"] == 1


def test_private_generated_eval_mock_duplicate_and_mojibake_rows_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "mixed.jsonl"
    good = "Public corpus evidence supports candidate learning with traceable provenance."
    _jsonl(
        source,
        [
            {"text": good, "license": "CC BY-SA 4.0", "language": "en"},
            {"text": good, "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "This private password material must be rejected.", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "Generated by model output and therefore not evidence.", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "This eval row from seed 33033 must be rejected.", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "AtanorSeedConcept42 sector 9 is forbidden.", "license": "CC BY-SA 4.0", "language": "en"},
            {"text": "Mojibake Ã¼ text should be rejected.", "license": "CC BY-SA 4.0", "language": "en"},
        ],
    )

    result = build_public_corpus_shard(
        PublicCorpusBuilderConfig(
            input_file=str(source),
            source_name="fixture",
            license_hint="CC BY-SA 4.0",
            language="en",
            output_dir=str(tmp_path / "approved"),
            dry_run=True,
            execute=False,
        )
    )

    assert result.rows_accepted == 1
    assert result.duplicate_rows == 1
    reasons = result.rejection_reasons
    assert "duplicate_normalized_text" in reasons
    assert "private_marker" in reasons
    assert "generated_marker" in reasons
    assert "eval_marker" in reasons
    assert "mock_marker" in reasons
    assert "mojibake" in reasons
