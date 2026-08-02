from __future__ import annotations

import json
from pathlib import Path

import pytest

from cgsr.ingestion.accumulator import VerifiedStore
from cgsr.ingestion.decomposer import decompose_sentence, extract_case_roles
from cgsr.ingestion.source_reader import make_source_sentences
from cgsr.ingestion.verification_gate import verify_sentence


def _init_store(root: Path) -> None:
    (root / "indexes").mkdir(parents=True)
    (root / "quarantine").mkdir(parents=True)
    schema = json.loads((Path(__file__).resolve().parents[4] / "data" / "cloud_brain" / "verified_store_v0" / "schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((Path(__file__).resolve().parents[4] / "data" / "cloud_brain" / "verified_store_v0" / "manifest.json").read_text(encoding="utf-8"))
    (root / "schema.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for rel in [
        "concepts.jsonl",
        "relations.jsonl",
        "evidence.jsonl",
        "case_frames.jsonl",
        "indexes/dedupe_index.jsonl",
        "indexes/source_index.jsonl",
        "quarantine/rejected.jsonl",
    ]:
        (root / rel).write_text("", encoding="utf-8")


def _source(text: str):
    return make_source_sentences(
        [text],
        source_name="Korean Wikipedia",
        source_type="wikipedia",
        license="CC BY-SA 4.0",
        document_id="unit",
        title="Unit",
        url="https://ko.wikipedia.org/wiki/Unit",
    )[0]


def test_source_reader_attaches_required_provenance() -> None:
    sentence = _source("쿠버네티스는 컨테이너를 관리한다.")
    assert sentence.language == "ko"
    assert sentence.source_type == "wikipedia"
    assert sentence.license == "CC BY-SA 4.0"
    assert sentence.source_hash


def test_verification_rejects_mock_templates() -> None:
    sentence = _source("AtanorSeedConcept123 sector 88은 합성 템플릿이다.")
    decision = verify_sentence(sentence)
    assert decision.status == "rejected"
    assert decision.reason == "mock_template_signal"


def test_verification_rejects_missing_license() -> None:
    sentence = make_source_sentences(
        ["쿠버네티스는 컨테이너를 관리한다."],
        source_name="Unknown",
        source_type="wikipedia",
        license="",
    )[0]
    decision = verify_sentence(sentence)
    assert decision.status == "rejected"
    assert decision.reason == "missing_or_disallowed_license"

