from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.verified_payload_feeder import PayloadSourcePolicy, VerifiedPayloadFeeder


def _write_payloads(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_feeder_discovers_web_producer_subdir_and_excludes_rejected(tmp_path: Path) -> None:
    # The web producer writes approved payloads into approved_payloads/web_feeds/;
    # the consumer must look there (else cumulative learning never sees them) but
    # never consume approved_payloads/rejected/.
    src = tmp_path / "approved_payloads"
    (src / "web_feeds").mkdir(parents=True)
    (src / "rejected").mkdir(parents=True)
    _write_payloads(
        src / "web_feeds" / "approved_payloads_x.jsonl",
        [{"source_id": "wf-1", "source_type": "local_public_corpus_shard", "text": "Paris is the capital of France.", "language": "en", "license_hint": "CC BY-SA 4.0", "target_store": "verified_store_v0_candidate"}],
    )
    _write_payloads(
        src / "rejected" / "approved_payloads_bad.jsonl",
        [{"source_id": "rej-1", "text": "must never be consumed", "is_private": True}],
    )
    feeder = VerifiedPayloadFeeder(source_dir=src)
    discovered = [str(p) for p in feeder._discovery_paths()]
    assert any("web_feeds" in p for p in discovered)
    assert not any("rejected" in p.casefold() for p in discovered)
    result = feeder.run_once()
    assert result.state == "payloads_available"
    assert result.approved_payloads_available >= 1


def test_feeder_reports_no_source_without_faking_payloads(tmp_path: Path) -> None:
    feeder = VerifiedPayloadFeeder(source_dir=tmp_path / "missing")
    result = feeder.run_once()
    assert result.state == "no_approved_payload_source"
    assert result.payloads_accepted == 0
    assert result.mock_growth is False


def test_feeder_accepts_only_policy_safe_public_rows(tmp_path: Path) -> None:
    source = tmp_path / "payloads.jsonl"
    _write_payloads(
        source,
        [
            {
                "source_type": "manual_public_sentence",
                "source_id": "manual:1",
                "text": "쿠버네티스는 컨테이너를 관리합니다.",
                "language": "ko",
                "license": "CC BY-SA 4.0",
                "source_url_or_path": "manual://public/1",
            },
            {
                "source_type": "manual_public_sentence",
                "source_id": "private:1",
                "text": "개인 대화는 클라우드 학습에 들어가면 안 됩니다.",
                "language": "ko",
                "license": "CC BY-SA 4.0",
                "is_private": True,
            },
            {
                "source_type": "manual_public_sentence",
                "source_id": "generated:1",
                "text": "생성 답변은 근거가 아닙니다.",
                "language": "ko",
                "license": "CC BY-SA 4.0",
                "is_generated": True,
            },
            {
                "source_type": "manual_public_sentence",
                "source_id": "eval:1",
                "text": "평가 행은 학습에 쓰지 않습니다.",
                "language": "ko",
                "license": "CC BY-SA 4.0",
                "is_eval_row": True,
            },
            {
                "source_type": "local_semantic_acceleration_batch",
                "source_id": "mock:1",
                "text": "AtanorSeedConcept000001 sector 7",
                "language": "en",
                "license": "proof",
            },
        ],
    )
    feeder = VerifiedPayloadFeeder(source_paths=[source], source_dir=tmp_path / "unused_default_dir", policy=PayloadSourcePolicy())
    result = feeder.run_once()
    assert result.state == "payloads_available"
    assert result.payloads_accepted == 1
    assert result.payloads_rejected == 4
    assert result.payloads[0].source_id == "manual:1"
    assert "private_payload_rejected" in result.last_rejection_reasons
    assert "generated_payload_rejected" in result.last_rejection_reasons
    assert "eval_row_rejected" in result.last_rejection_reasons
    assert "source_type_not_allowed" in result.last_rejection_reasons
