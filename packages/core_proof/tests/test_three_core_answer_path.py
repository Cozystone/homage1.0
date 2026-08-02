from __future__ import annotations

import json
from pathlib import Path

from packages.core_proof.three_core_answer_path import (
    detect_mock_scaffolds,
    encode_query_to_sqc,
    run_prompt_proof,
    run_three_core_answer_path_proof,
)


def test_sqc_encodes_query_as_u32_bitfields() -> None:
    sqc = encode_query_to_sqc("쿠버네티스가 뭐야?")
    atoms = sqc["encoded_concepts"]
    assert sqc["used"] is True
    assert atoms
    assert sqc["compression_form"].startswith("u32_bitfield")
    assert all(0 <= atom["packed_u32"] <= 0xFFFFFFFF for atom in atoms)
    assert all(len(atom["bitmap"]) == 32 for atom in atoms)
    assert sqc["memory_bytes"] == len(atoms) * 4


def test_prompt_proof_uses_three_core_axes_without_llm_or_local_write() -> None:
    record = run_prompt_proof("Local Brain과 Cloud Brain 차이를 쉽게 말해줘.")
    assert record["sqc"]["used"] is True
    assert record["seed_rail"]["used"] is True
    assert record["wave_graph"]["used"] is True
    assert len(record["wave_graph"]["candidate_paths"]) >= 2
    assert record["surface"]["used"] is True
    assert record["trace_hidden_by_default"] is True
    assert record["external_llm_used"] is False
    assert record["sllm_used"] is False
    assert record["local_write"] is False


def test_mock_detector_flags_canned_prompt_specific_source() -> None:
    scan = detect_mock_scaffolds(
        "Kubernetes is a container orchestration system.",
        'if "kubernetes" in query: return "fixed paragraph"',
    )
    assert scan["risky_scaffold"] is True
    assert "prompt_specific_return_pattern_seen_in_source" in scan["flags"]


def test_mock_detector_flags_default_internal_trace_leakage() -> None:
    scan = detect_mock_scaffolds("Local Brain -> Cloud Brain -> Working Memory")
    assert scan["production_violation"] is True
    assert "internal_trace_leakage" in scan["flags"]


def test_three_core_proof_writes_json_and_markdown(tmp_path: Path) -> None:
    proof = run_three_core_answer_path_proof(
        ["쿠버네티스가 뭐야?", "Q-Cortex가 실제 양자컴퓨터가 아니라는 점을 설명해줘."],
        output_root=tmp_path,
    )
    assert proof["executive_verdict"] in {"PASS", "PARTIAL"}
    assert proof["updated_scores"]["holographic_wave_graph_score"] <= 70
    assert proof["external_llm_used"] is False
    assert proof["external_sllm_used"] is False
    paths = proof["artifact_paths"]
    json_path = Path(paths["json"])
    md_path = Path(paths["markdown"])
    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["schema"] == "atanor.three-core-answer-path-proof.v1"
    assert "Three-Core" in md_path.read_text(encoding="utf-8")
