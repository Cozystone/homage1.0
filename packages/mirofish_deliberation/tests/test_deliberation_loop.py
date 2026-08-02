"""The multi-step loop must be GROUNDED (findings from real ledger files), EVOLVING
(objections raised in round N resolved by round N+1 probes with cited observations),
and READ-ONLY (ledger bytes untouched)."""
from __future__ import annotations

import json
from pathlib import Path

from packages.mirofish_deliberation.deliberation_loop import run_deliberation_loop


def _write_ledger(root: Path, lines: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence_ledger.jsonl").write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )


def _evidence(eid: str, subject: str, target: str, voice: str) -> dict:
    return {
        "evidence_id": eid,
        "source_label": subject,
        "target_label": target,
        "row": {"relation": "IS_A", "provenance": {"source_id": voice}},
    }


def test_consensus_met_approves_in_one_round(tmp_path):
    _write_ledger(tmp_path, [
        _evidence("e1", "커피", "음료", "wiki-ko"),
        _evidence("e2", "커피", "음료", "wiktionary"),
    ])
    res = run_deliberation_loop("커피", ledger_root=tmp_path)
    assert res.promotion_recommendation == "approve_for_review"
    assert res.rounds_run == 1 and res.fixed_point
    assert res.requires_manual_approval is True
    # grounded: the builder statement carries the observed ledger view
    builder = next(s for s in res.transcript if s.role == "builder")
    assert builder.observed and builder.observed["max_voices"] == 2


def test_single_voice_probes_then_asks_for_more_evidence(tmp_path):
    _write_ledger(tmp_path, [_evidence("e1", "팔란티어", "기업", "wiki-ko")])
    res = run_deliberation_loop("팔란티어", ledger_root=tmp_path)
    assert res.promotion_recommendation == "needs_more_evidence"
    # MULTI-STEP: round 2 ran a real re-read probe and recorded what it observed
    assert res.rounds_run == 2
    probe = next(s for s in res.transcript if s.probe == "consensus_ledger.evidence_for_label")
    assert probe.round_no == 2 and probe.observed["max_voices"] == 1
    assert res.objections_open and res.objections_open[0]["kind"] == "insufficient_evidence"


def test_isolated_contradiction_resolves_across_rounds(tmp_path):
    _write_ledger(tmp_path, [
        _evidence("e1", "지구", "행성", "wiki-ko"),
        _evidence("e2", "지구", "행성", "britannica"),
    ])
    # a curated-judge contradiction is ON RECORD but was quarantined, never promoted
    (tmp_path / "curated_quarantine.jsonl").write_text(
        json.dumps({"key": "지구|IS_A|평면", "verdict": "contradicted"}) + "\n",
        encoding="utf-8",
    )
    res = run_deliberation_loop("지구", ledger_root=tmp_path)
    # round 1 raises the objection; round 2 verifies isolation against promoted_keys
    assert res.rounds_run == 2
    assert res.promotion_recommendation == "approve_for_review"
    assert any(o["kind"] == "contradictions_on_record" for o in res.objections_resolved)
    verify = next(s for s in res.transcript if s.stance == "verify-isolation")
    assert verify.observed == {"leaked": []}


def test_leaked_contradiction_blocks(tmp_path):
    _write_ledger(tmp_path, [
        _evidence("e1", "지구", "행성", "wiki-ko"),
        _evidence("e2", "지구", "행성", "britannica"),
    ])
    (tmp_path / "curated_quarantine.jsonl").write_text(
        json.dumps({"key": "지구|IS_A|평면", "verdict": "contradicted"}) + "\n", encoding="utf-8")
    (tmp_path / "promoted_keys.jsonl").write_text(
        json.dumps({"key": "지구|IS_A|평면"}) + "\n", encoding="utf-8")
    res = run_deliberation_loop("지구", ledger_root=tmp_path)
    assert res.promotion_recommendation == "blocked"
    assert any(o["kind"] == "contradictions_on_record" for o in res.objections_open)


def test_privacy_flag_is_human_only_and_blocks(tmp_path):
    _write_ledger(tmp_path, [
        _evidence("e1", "사용자", "개인", "local"),
        _evidence("e2", "사용자", "개인", "local2"),
    ])
    res = run_deliberation_loop("사용자", ledger_root=tmp_path,
                                privacy_report={"private_data_present": True})
    assert res.promotion_recommendation == "blocked"
    assert res.objections_open[0]["resolvable"] is False


def test_loop_is_read_only(tmp_path):
    _write_ledger(tmp_path, [_evidence("e1", "커피", "음료", "wiki-ko")])
    ledger_file = tmp_path / "evidence_ledger.jsonl"
    before = ledger_file.read_bytes()
    res = run_deliberation_loop("커피", ledger_root=tmp_path)
    assert ledger_file.read_bytes() == before
    assert not (tmp_path / "promoted_keys.jsonl").exists()
    assert res.production_store_mutated is False and res.candidate_promotion is False
