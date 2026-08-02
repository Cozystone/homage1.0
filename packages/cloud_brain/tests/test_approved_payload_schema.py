from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.verified_payload_feeder import VerifiedPayloadFeeder
from packages.cloud_brain.web_approved_payload_feeder import SourceSpec, collect_approved_payloads


REQUIRED_SCHEMA_KEYS = {
    "payload_id",
    "source_type",
    "source_id",
    "source_url_or_path",
    "source_title",
    "license_hint",
    "language",
    "text",
    "normalized_text",
    "provenance_hash",
    "raw_text_hash",
    "normalized_text_hash",
    "collected_at",
    "collector",
    "collector_version",
    "is_private",
    "is_generated",
    "is_eval_row",
    "is_mock",
    "quality_flags",
}


def test_approved_payload_jsonl_contains_required_schema_keys(tmp_path: Path) -> None:
    result = collect_approved_payloads(
        [
            SourceSpec(
                source_type="manual_public_sentence",
                source_id="schema:manual",
                source_url_or_path="manual://schema-public",
                source_title="Schema public sentence",
                license_hint="CC BY-SA 4.0 test fixture",
                text="지식 그래프는 개념과 관계를 표현합니다.",
            )
        ],
        output_dir=tmp_path / "approved",
        rejected_dir=tmp_path / "rejected",
        manifest_path=tmp_path / "manifest.json",
        dry_run=False,
    )
    assert result.approved_payload_path is not None
    rows = [json.loads(line) for line in Path(result.approved_payload_path).read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert REQUIRED_SCHEMA_KEYS <= set(row)
    assert row["collector"] == "atanor_web_feeder"
    assert row["collector_version"] == "approved_web_feeder_v1"
    assert row["is_private"] is False
    assert row["is_generated"] is False
    assert row["is_eval_row"] is False
    assert row["is_mock"] is False
    assert row["raw_text_hash"] != row["normalized_text_hash"] or row["text"] == row["normalized_text"]


def test_schema_rejects_missing_public_provenance_unless_manual_source_id_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "payloads.jsonl"
    source.write_text(
        json.dumps(
            {
                "source_type": "manual_public_sentence",
                "source_id": "",
                "source_url_or_path": "",
                "license_hint": "CC BY-SA 4.0 test fixture",
                "language": "ko",
                "text": "지식 그래프는 개념과 관계를 표현합니다.",
                "provenance_hash": "",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    result = VerifiedPayloadFeeder(source_paths=[source], source_dir=tmp_path / "unused_default_dir").run_once()
    assert result.payloads_accepted == 0
    assert result.payloads_rejected == 1
    assert result.last_rejection_reasons == ["missing_provenance"]
